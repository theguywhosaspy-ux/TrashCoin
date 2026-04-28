import socket
import struct
import json
import random
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
MCAST_GRP = '239.255.0.1'
MCAST_PORT = 5007

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)


sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


sock.bind(('', MCAST_PORT))


mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

print(f"Listening for JSON data on {MCAST_GRP}:{MCAST_PORT}...")


def mint(num_trash: int):

    coin = 0.01* num_trash + 0.001 * random.randint(0, 100)
    return coin


while True:
    try:

        data, addr = sock.recvfrom(1024)
        

        with open("chacha.key", "rb") as key_file:
            loaded_key = key_file.read()
            
        chacha = ChaCha20Poly1305(loaded_key)
        nonce = data[:12]
        ci_text = data[12:]

        decrypt_data = chacha.decrypt(nonce, ci_text, None)
    
        
        
        json_data = json.loads(decrypt_data.decode('utf-8'))
        print(f"Received from {addr}: {json_data}")
        num_trash = json_data["trash_count"]
        coin = mint(num_trash)
        print(f"\ngenerated {coin} trashcoin!")
        
    except json.JSONDecodeError:
        print("Received malformed JSON data")
    except Exception as e:
        print(f"Error: {e}")
