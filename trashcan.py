import RPi.GPIO as GPIO

from mfrc522 import SimpleMFRC522

import time 
import math
import socket
import json
from enum import Enum



TRIG = 23
ECHO = 24
PIN = 5
TTL = 1

class TrashCanState(Enum):
    """Trash Can State Enum Class"""
    INIT_CAN = 0 
    READER_STANDBY = 1
    OPEN_CAN = 2 
    DETECT_TRASH = 3
    CLOSE_CAN = 4 
    GENERATE_TOKEN = 5   
    SEND_TOKEN = 6
    
class TrashPayload:
    def __init__(self,device:str , location: str |None, student_id: str | None, trash_count: int | None, key: str | None) -> None:
        self.device:str  = device
        self.location: str | None = location
        self.student_id: str | None = student_id
        self.trash_count: int | None = trash_count
        self.key: str |  None = key
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
        self.last_dist: float = 100
        self.reader = SimpleMFRC522()
        self.state: TrashCanState  = TrashCanState.INIT_CAN 
        self.key: str ="jsfekliajf390423klj43n3kj2ln4"
        self.msg: dict = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, TTL)
        
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
        data = TrashPayload(self.can_id, self.location, self.student_id, self.trash_ct, self.key)
        self.msg = data.__dict__
    
    def __send_message(self):
        message = json.dumps(self.msg).encode('utf-8')
        self.sock.sendto(message, (self.mcast_grp, self.mcast_prt))

        
    
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
            _, self.student_id = self.reader.read()
            self.student_id = self.student_id.strip()
            print(f"\nHello student: {self.student_id}")

            
    def trashcan_run(self):
        match self.state:
            
            case TrashCanState.INIT_CAN:
                self.student_id = None
                self.trash_ct = 0
                self.state = TrashCanState.READER_STANDBY
            
            case TrashCanState.READER_STANDBY:
                self.__read_id()
                if self.student_id:
                    self.state = TrashCanState.OPEN_CAN


            case TrashCanState.OPEN_CAN:
                self.open_can()
                self.open = True
                self. end_time = time.time() + 5.0
                self.state = TrashCanState.DETECT_TRASH
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
            
            
Can_One = Trashcan("can-1", "Stingers")

while True:
    try:
        Can_One.trashcan_run()
        print("\n" , Can_One.state)
    except:
        print("\ncleaning up")
        GPIO.cleanup()