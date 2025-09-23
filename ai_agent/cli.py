# cli.py
import logging
import sys, requests, json

logger = logging.getLogger(__name__)


def stream_chat(base_url: str, message: str):
    url = f"{base_url.rstrip('/')}/chat"
    with requests.get(
        url,
        params={"message": message},
        stream=True,
        headers={"Accept": "text/event-stream"},
    ) as r:
        r.raise_for_status()
        event, data_lines = None, []
        for raw in r.iter_lines(decode_unicode=True):
            if raw is None:
                continue
            line = raw.strip()

            if not line:  # frame terminator
                if data_lines:
                    payload = "\n".join(data_lines)
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        obj = {"raw": payload}
                    if event == "token":
                        delta = obj.get("delta", "")
                        print(delta, end="", flush=True)
                    elif event == "end":
                        print()  # newline after final token
                        return
                    elif event == "error":
                        print(f"\n[error] {obj.get('message')}", file=sys.stderr)
                        return
                event, data_lines = None, []
                continue

            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].lstrip())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            'Usage: python cli.py "your message" [http://127.0.0.1:8100]',
            file=sys.stderr,
        )
        sys.exit(1)
    message = sys.argv[1]
    base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8100"
    stream_chat(base, message)
