import socket
import struct
import json
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
MCAST_GRP = '239.255.0.1'
MCAST_PORT = 5007

# 1. Create a UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

# 2. Allow multiple listeners on the same port
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

# 3. Bind to the server address
# On Windows, bind to the multicast address; on Linux, often bind to '' (all interfaces)
sock.bind(('', MCAST_PORT))

# 4. Join the multicast group
mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

print(f"Listening for JSON data on {MCAST_GRP}:{MCAST_PORT}...")

while True:
    try:
        # Receive data
        data, addr = sock.recvfrom(1024)
        
        # 5. Decode and parse JSON
        
        
        
        with open("chacha.key", "rb") as key_file:
            loaded_key = key_file.read()
        print(len(loaded_key))
        chacha = ChaCha20Poly1305(loaded_key)
        nonce = data[:12]
        ci_text = data[12:]

        decrypt_data = chacha.decrypt(nonce, ci_text, None)
    
        
        
        json_data = json.loads(decrypt_data.decode('utf-8'))
        print(f"Received from {addr}: {json_data}")
        
    except json.JSONDecodeError:
        print("Received malformed JSON data")
    except Exception as e:
        print(f"Error: {e}")
