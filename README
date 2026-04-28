# TrashCoin

A DePIN (Decentralized Physical Infrastructure Network) incentive system that rewards students with TrashCoin for disposing of waste properly. RFID-authenticated smart trash cans detect deposits via ultrasonic sensors, encrypt payloads with ChaCha20-Poly1305, and broadcast them over UDP multicast to a validator that mints tokens into per-student wallets.

![TrashCoin Dashboard](dashboard.png)

## How It Works

1. **Student taps RFID card** → the trash can authenticates the student
2. **Lid opens** → ultrasonic sensor takes a baseline distance reading
3. **Student deposits trash** → 5-second window to throw items in
4. **Lid closes** → sensor measures again and compares to baseline to count items
5. **Encrypted payload sent** → ChaCha20-Poly1305 encrypted message broadcast via UDP multicast
6. **Validator receives & verifies** → decrypts, validates, mints TrashCoin into the student's wallet
7. **Dashboard updates** → live web UI shows wallets, transactions, and device status

## Components

| File | Role |
|---|---|
| `trashcan.py` | Raspberry Pi state machine — RFID reader, servo lid, ultrasonic sensor, encrypted multicast sender |
| `validator.py` | UDP multicast listener, decryption, payload validation, SQLite ledger, Flask dashboard API |
| `dashboard.html` | Live auto-refreshing web dashboard (served by the validator) |
| `key_gen.py` | One-time ChaCha20-Poly1305 key generator |

## Setup

### Prerequisites

- Raspberry Pi with GPIO access
- HC-SR04 ultrasonic sensor (TRIG → GPIO 23, ECHO → GPIO 24)
- SG90 servo motor (signal → physical pin 5)
- MFRC522 RFID reader + cards
- Python 3.10+

### Install Dependencies

**On the Pi (trash can):**
```bash
pip install RPi.GPIO mfrc522 cryptography
```

**On the validator (Pi or any machine on the same network):**
```bash
pip install flask cryptography
```

### Generate Shared Key

Run once and copy `chacha.key` to both the trash can and the validator:
```bash
python key_gen.py
```

### Run

**Start the validator first:**
```bash
python validator.py
```
Dashboard available at `http://<validator-ip>:8080`

**Then start the trash can:**
```bash
python trashcan.py
```

## Configuration

| Constant | File | Default | Description |
|---|---|---|---|
| `TRIG` | trashcan.py | 23 | Ultrasonic trigger GPIO (BCM) |
| `ECHO` | trashcan.py | 24 | Ultrasonic echo GPIO (BCM) |
| `PIN` | trashcan.py | 5 | Servo signal pin (BOARD) |
| `MCAST_GRP` | both | 239.255.0.1 | Multicast group address |
| `MCAST_PORT` | both | 5007 | Multicast port |
| `WEB_PORT` | validator.py | 8080 | Dashboard HTTP port |

## Custodian Mode

Writing `custodian` to an RFID card creates an admin card. Tapping it toggles the lid open for maintenance or emptying. Tap again to close and resume normal operation.

## License

MIT
