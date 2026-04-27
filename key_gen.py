from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
import os


with open("chacha.ppk", "wb") as key_file:
    key_file.write(ChaCha20Poly1305.generate_key() )
    
with open("chacha.ppk", "rb") as key_file:
    loaded_key = key_file.read()

chacha = ChaCha20Poly1305(loaded_key)
DATA = b"HELLO"
nonce = os.urandom(12)
ci_text= chacha.encrypt(nonce ,DATA, None)


pay_load = nonce + ci_text


print(pay_load)

nonce_2 = pay_load[:12]
ci_2 = pay_load[12:]

decrypt_data = chacha.decrypt(nonce_2, ci_2, None)

print(decrypt_data)