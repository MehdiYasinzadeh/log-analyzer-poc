import time
import random
import grpc

CATEGORIES = [
    b"\x0a\x05books",
    b"\x0a\x0abinoculares",
    b"\x0a\x0atelescopes",
    b"\x0a\x0baccessories",
    b"\x0a\x06travel"
]

def main():
    print("[Paced Traffic] Starting gentle paced traffic generator for AdService (1 call every 2.5s)...")
    channel = grpc.insecure_channel("localhost:9555")
    unary = channel.unary_unary(
        "/oteldemo.AdService/GetAds",
        request_serializer=lambda x: x,
        response_deserializer=lambda x: x
    )

    count = 0
    while True:
        try:
            cat = random.choice(CATEGORIES)
            unary(cat, timeout=2.0)
            count += 1
            if count % 10 == 0:
                print(f"[Paced Traffic] Sent {count} gentle requests successfully (system cool).")
        except grpc.RpcError as e:
            # During chaos injection (adFailure), this will catch the UNAVAILABLE status!
            code = e.code()
            print(f"[Paced Traffic] Expected chaos response: {code.name} - {e.details()}")
        except Exception as ex:
            print(f"[Paced Traffic] Request note: {ex}")

        time.sleep(2.5)

if __name__ == "__main__":
    main()
