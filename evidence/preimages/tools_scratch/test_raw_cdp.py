import asyncio
import json
import urllib.request

import websockets


async def test_raw():
    v = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/version").read().decode("utf-8"))
    ws_url = v["webSocketDebuggerUrl"]
    print("Connecting to ws_url:", ws_url)
    async with websockets.connect(ws_url) as ws:
        print("Connected via websockets!")
        req = {"id": 1, "method": "Browser.getVersion"}
        await ws.send(json.dumps(req))
        resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
        print("Received response:", resp)

        req2 = {"id": 2, "method": "Target.getTargets"}
        await ws.send(json.dumps(req2))
        resp2 = await asyncio.wait_for(ws.recv(), timeout=5.0)
        print("Received targets response:", resp2[:200])

def main() -> None:
    asyncio.run(test_raw())

if __name__ == "__main__":
    main()
