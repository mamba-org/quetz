import json
import signal
from multiprocessing import active_children

from starlette.requests import Request as ASGIRequest
from starlette.responses import Response as ASGIResponse


class AsyncPathMapDispatch:
    # dummy server, copied from authlib tests
    def __init__(self, path_maps):
        self.path_maps = path_maps

    async def __call__(self, scope, receive, send):
        request = ASGIRequest(scope, receive=receive)

        rv = self.path_maps[request.url.path]
        status_code = rv.get('status_code', 200)
        body = rv.get('body')
        headers = rv.get('headers', {})
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        else:
            if isinstance(body, str):
                body = body.encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded'

        response = ASGIResponse(
            status_code=status_code,
            content=body,
            headers=headers,
        )
        await response(scope, receive, send)


class Interrupt:
    # Interrupt child when SIGALRM is received.
    # Useful to kill the server when it is correctly launched, using a timeout.
    def _handle_interrupt(self, signum, frame):
        for p in active_children():
            p.terminate()
            p.join()

    def __enter__(self):
        signal.signal(signal.SIGALRM, self._handle_interrupt)

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
