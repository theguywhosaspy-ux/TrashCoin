import RPi.GPIO as GPIO

from mfrc522 import SimpleMFRC522
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

import os
import time 
import math
import socket
import json
from enum import Enum



TRIG = 23
ECHO = 24
PIN = 5
TTL = 1
CUSTODIAN = "custodian"

class TrashCanState(Enum):
    """Trash Can State Enum Class"""
    INIT_CAN = 0 
    READER_STANDBY = 1
    OPEN_CAN = 2 
    DETECT_TRASH = 3
    CLOSE_CAN = 4 
    GENERATE_TOKEN = 5   
    SEND_TOKEN = 6
    CUSTODIAN = 7
    POST_STATUS = 8
    
class TrashPayload:
    def __init__(self,device:str , location: str |None, student_id: str | None, trash_count: int | None, full:bool) -> None:
        self.device:str  = device
        self.location: str | None = location
        self.student_id: str | None = student_id
        self.trash_count: int | None = trash_count
        self.full: bool = full
        self.time_stamp : float = time.time()

class Trashcan:
    """_summary_
    """
    
    def __init__(self, can_id: str, location: str) -> None:
        self.can_id: str = can_id
        self.mcast_grp: str = "239.255.0.1"
        self.mcast_prt: int = 5007
        self.student_id: str | None = None
        self.trash_ct: int = 0 
        self.full: bool = False
        self.location: str = location
        self.open: bool = False
        self.end_time: float = 0.0
        self.dist: float = 0
        self.last_dist: float = 0
        self.reader = SimpleMFRC522()
        self.state: TrashCanState  = TrashCanState.INIT_CAN 
        self.msg: dict = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, TTL)
        self.admin_lock: bool =False
        self.full: bool = False
        self.count: int = 0
        
        
    def __get_distance(self):
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(TRIG, GPIO.OUT)
            GPIO.setup(ECHO, GPIO.IN)
            time.sleep(0.2)
            # Ensure Trigger is low
            GPIO.output(TRIG, False)
            time.sleep(0.000002)

            # Trigger pulse (10 microseconds)
            GPIO.output(TRIG, True)
            time.sleep(0.00001)
            GPIO.output(TRIG, False)
            # Measure echo time
            
            while GPIO.input(ECHO) == 0:
                pulse_start = time.time()
            while GPIO.input(ECHO) == 1:
                pulse_end = time.time()

            duration = pulse_end - pulse_start
            distance = (duration * 34300) / 2 
            self.dist = round(distance, 2)
        except:
            GPIO.cleanup()
    
    def check_for_trash(self):
        
        self.__get_distance()
        if not math.isclose(self.dist, self.last_dist, abs_tol = 1.0): 
            print(f"Distance: {self.dist} cm")
            print("\nTrash Detected")
            self.trash_ct += 1
        self.last_dist = self.dist

    def __generate_message(self):
        data = TrashPayload(self.can_id, self.location, self.student_id, self.trash_ct, self.full)
        self.msg = data.__dict__
    
    
    def __encrypt_message(self, data:bytes):
        with open("chacha.key", "rb") as key_file:
            loaded_key = key_file.read()

        chacha = ChaCha20Poly1305(loaded_key)
        nonce = os.urandom(12)
        ci_text= chacha.encrypt(nonce ,data, None)
        payload = nonce + ci_text
           
        return payload
        
    
    def __send_message(self):
        
        
        message = json.dumps(self.msg).encode('utf-8')
        payload = self.__encrypt_message(message)
        self.sock.sendto(payload, (self.mcast_grp, self.mcast_prt))

        
    
    def __SetAngle(self, angle:int):
        GPIO.setmode(GPIO.BOARD)

        GPIO.setup(PIN, GPIO.OUT)
        pwm=GPIO.PWM(PIN, 50)
        pwm.start(0)
        duty = angle / 18 + 2
        GPIO.output(PIN,True)
        pwm.ChangeDutyCycle(duty)
        time.sleep(1)
        GPIO.output(PIN,False)
        pwm.ChangeDutyCycle(0)
        
    def open_can(self):
        self.__SetAngle(180)
        self.open =True

    def close_can(self):
        self.__SetAngle(45)
        self.open = False
        
    def __read_id(self):
        id, text = self.reader.read_no_block()
        if id is not None:
            self.student_id = text.strip()
            print(f"\nHello student: {self.student_id}")
        else:
            self.student_id = None

    def __check_custodian(self):
        if self.student_id == CUSTODIAN:
            self.admin_lock = not self.admin_lock

    
    def trashcan_run(self):
        match self.state:
            
            case TrashCanState.INIT_CAN:
                self.dist = self.last_dist
                self.student_id = None
                self.trash_ct = 0
                self.state = TrashCanState.READER_STANDBY
                self.admin_lock = False
                
            case TrashCanState.READER_STANDBY:
                if self.count < 60:
                    self.__read_id()
                    if self.student_id:
                        self.__check_custodian()
                        if self.admin_lock:
                            self.state = TrashCanState.CUSTODIAN
                        else:
                            self.state = TrashCanState.OPEN_CAN
                    self.count += 1
                    time.sleep(0.5)  
                else:
                    self.count = 0 
                    self.state = TrashCanState.POST_STATUS

            case TrashCanState.OPEN_CAN:
                self. end_time = time.time() + 2.0
                self.state = TrashCanState.DETECT_TRASH
                self.open_can()
                self.open = True
                GPIO.cleanup()
            
            case TrashCanState.DETECT_TRASH:
                
                while time.time() < self.end_time:
                    self.check_for_trash()
                    time.sleep(0.1)
                self.state = TrashCanState.CLOSE_CAN
                GPIO.cleanup()
                
            case TrashCanState.CLOSE_CAN:
                self.close_can()
                self.open = False
                self.state = TrashCanState.GENERATE_TOKEN
                GPIO.cleanup()
            
            case TrashCanState.GENERATE_TOKEN:
                self.__generate_message()
                print(self.msg)
                self.state = TrashCanState. SEND_TOKEN

            case TrashCanState.SEND_TOKEN:
                self.__send_message()
                self.state = TrashCanState.INIT_CAN
                
            case TrashCanState.CUSTODIAN:
                if not self.open:
                    self.open_can()
                    self.open = True
                    GPIO.cleanup()
                if self.open:
                    self.__read_id()
                    if self.student_id:
                        self.__check_custodian()
                        if not self.admin_lock:
                            self.close_can()
                            self.open = False
                            self.state = TrashCanState.INIT_CAN
                            
            case TrashCanState.POST_STATUS:
                self.__get_distance()
                if self.dist >= 2.7 and self.dist < 10:
                    self.full = True
                self.__generate_message()
                self.__send_message()
                self.full = False
                self.state = TrashCanState.READER_STANDBY
            
Can_One = Trashcan("can-1", "Stingers")

while True:
    try:
        Can_One.trashcan_run()
        print("\n" , Can_One.state)
    except:
        print("\ncleaning up")
        GPIO.cleanup()