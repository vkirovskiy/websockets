#!/usr/bin/env python

import asyncio
import websockets
import json

updateint = 0.1
connected = set() 
xyposition = [0,0]
queue = asyncio.Queue(maxsize=10)

@asyncio.coroutine
def producer():
    global connected
    global updateint
    global xyposition
    global queue

    yield from asyncio.sleep(updateint)
    
    try:
        line = queue.get_nowait()
        print(line)
    except RuntimeError:
        line = ''
    except asyncio.queues.QueueEmpty:
        line = ''

    js = { 'clients': len(connected), 'data': xyposition, 'log': str(line) }
    return json.dumps(js)

def set_position(x,y):
    global xyposition
    xyposition = [x,y]
    
@asyncio.coroutine
def recv_data(message):
    
    #print("< {}".format(message))
    try:
        js = json.loads(message)
        set_position(js['xy'][0], js['xy'][1])
    except ValueError:
        pass
    except KeyError:
        pass

def register_client(websocket):
    global connected
    connected.add(websocket)

def unregister_client(websocket):
    global connected
    connected.remove(websocket) 

@asyncio.coroutine
def wshandler(websocket, path):
    
    register_client(websocket)
    
    while True:
        listener_task = asyncio.async(websocket.recv())
        producer_task = asyncio.async(producer()) 

        done, pending = yield from asyncio.wait(
            [listener_task, producer_task],
            return_when=asyncio.FIRST_COMPLETED)

        if listener_task in done:
            try:
                message = listener_task.result()
                asyncio.async(recv_data(message))
                #print(websocket.remote_address)
            except websockets.exceptions.ConnectionClosed:
                yield from websocket.close()
                unregister_client(websocket)
                print("Connection closed")
                break

        else:
            listener_task.cancel()

        if producer_task in done:
            message = producer_task.result()
            if isinstance(message, str):
                yield from websocket.send(message)
        else:
            producer_task.cancel() 

@asyncio.coroutine
def ffmpegd(bitrate):
    global queue

    ffmpeg = asyncio.create_subprocess_exec(
        "ffmpeg",
        "-v", "repeat+info",
        "-i", "/dev/video0",
        "-s", "720x576",
        "-r", "15",
        "-vcodec", "libx264",
        "-f", "flv",
        "-b:v", "300k",
        "-preset", "fast",
        "rtmp://192.168.2.6:1935/video/1"
        ,
        stderr=asyncio.subprocess.PIPE )
        
    proc = yield from ffmpeg    
    
    while True:
        try:
            data = yield from proc.stderr.readline()
            if queue.full():
                yield from queue.get()

            yield from queue.put(data.decode("utf8").rstrip())
            print(">>" + str(data.rstrip()))
            
        except:
            break

    yield from proc.wait()

wsserver = websockets.serve(wshandler, '192.168.2.3', 8080)

tasks = [ 
    asyncio.async(wsserver),
    asyncio.async(ffmpegd(1024))
]

#asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_until_complete(asyncio.wait(tasks))
asyncio.get_event_loop().run_forever()

