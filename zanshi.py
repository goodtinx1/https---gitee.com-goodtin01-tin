import os
import sys
import json
import pyaudio
import time
from vosk import Model, KaldiRecognizer
from pymodbus.client import ModbusSerialClient
from threading import Thread, Event

class VoiceFanControlSystem:
    def __init__(self):
        # Modbus RTU 配置
        self.modbus_config = {
            "port": "COM3",
            "baudrate": 9600,
            "bytesize": 8,
            "parity": 'E',
            "stopbits": 1,
            "timeout": 3
        }
        self.slave_address = 2    # Modbus从机地址
        self.fan_register = 0     # 控制风扇的寄存器地址
        self.max_retries = 2      # 最大重试次数
        self.retry_delay = 0.5    # 重试间隔(秒)

        # VOSK中文语音识别
        self.model_path = "C:/Users/17258/AppData/Local/Programs/Python/Python312/Lib/site-packages/vosk/vosk-model-small-cn-0.22"
                  
        self.model = Model(self.model_path)
        self.recognizer = KaldiRecognizer(self.model, 16000)
        self.audio = pyaudio.PyAudio()
        
        # 控制变量
        self.running = Event()
        self.fan_state = False
        self.client = None

    def modbus_connect(self):
        """建立Modbus连接"""
        print("\n正在连接Modbus设备...")
        try:
            self.client = ModbusSerialClient(
                method='rtu',  # 明确指定RTU模式
                port=self.modbus_config["port"],
                baudrate=self.modbus_config["baudrate"],
                bytesize=self.modbus_config["bytesize"],
                parity=self.modbus_config["parity"],
                stopbits=self.modbus_config["stopbits"],
                timeout=self.modbus_config["timeout"]
            )
            
            if not self.client.connect():
                raise ConnectionError("无法打开串口")
            
            # 测试读取寄存器
            test = self.client.read_holding_registers(
                address=self.fan_register,
                count=1,
                slave=self.slave_address
            )
            
            if test.isError():
                print("测试读取失败，尝试写入...")
            else:
                print(f"测试读取成功，寄存器值: {test.registers}")
                
            print("Modbus连接成功！")
            return True
        
        except Exception as e:
            print(f"连接失败: {str(e)}")
            print("请检查：1.串口连接 2.参数配置 3.从机地址")
            return False
            
    def control(self, state):
        """风扇控制函数"""
        value = 1 if state else 0
        print(f"\n准备{'开启' if state else '关闭'}风扇...")
        
        for attempt in range(self.max_retries + 1):
            try:
               # 方法1：尝试写入保持寄存器
                response = self.client.write_register(
                    address=self.fan_register,
                    value=value,
                    slave=self.slave_address
                )
                
                if response.isError():
                    print("尝试写入线圈寄存器...")
                    response = self.client.write_coil(
                        address=self.fan_register,
                        value=value,
                        slave=self.slave_address
                    )
                
                if not response.isError():
                    self.fan_state = state
                    print(f"控制成功！风扇已{'开启' if state else '关闭'}")
                    return True
                    
                print(f"尝试 {attempt + 1} 失败: {response}")
                
            except Exception as e:
                print(f"尝试 {attempt + 1} 异常: {str(e)}")
            
            if attempt < self.max_retries:
                time.sleep(self.retry_delay)
        
        print("控制失败：达到最大重试次数")
        return False

    def voice_command(self, text):
        """直接执行语音命令"""
        cleaned = text.replace(" ", "").replace("，", "").replace("。", "")
        print(f"\n识别到命令: {cleaned}")
        
        # 立即执行控制命令
        if any(cmd in cleaned for cmd in ["打开风扇", "开启风扇", "启动风扇"]):
            if not self.fan_state:
                self.control(True)
            else:
                print("风扇已是开启状态")
                
        elif any(cmd in cleaned for cmd in ["关闭风扇", "关掉风扇", "停止风扇"]):
            if self.fan_state:
                self.control(False)
            else:
                print("风扇已是关闭状态")
                
        elif "退出系统" in cleaned:
            self.running.clear()
            print("正在退出...")
            
        else:
            print("可用命令: 打开风扇, 关闭风扇, 退出系统")

    def voice_recognition(self):
        """语音识别线程"""
        stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=8192
        )
        
        print("\n语音控制已就绪，请说：")
        print("1. 打开风扇")
        print("2. 关闭风扇")
        print("3. 退出系统")
        
        while self.running.is_set():
            data = stream.read(4096, exception_on_overflow=False)
            if len(data) == 0:
                continue
                
            if self.recognizer.AcceptWaveform(data):
                result = json.loads(self.recognizer.Result())
                if 'text' in result and result['text']:
                    self.voice_command(result['text'])
        
        stream.stop_stream()
        stream.close()
        print("语音识别已停止")

    def start(self):
        """启动系统"""
        if not self.modbus_connect():
            return
            
        self.running.set()
        
        # 启动语音识别线程
        voice_thread = Thread(target=self.voice_recognition)
        voice_thread.daemon = True
        voice_thread.start()
        
        try:
            while self.running.is_set():
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n正在停止系统...")
        finally:  
            self.running.clear()
            voice_thread.join(timeout=1)
            self.client.close()
            self.audio.terminate()
            print("系统已关闭")

if __name__ == "__main__":
    system = VoiceFanControlSystem()
    system.start()