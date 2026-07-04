import struct
from Crypto.Cipher import AES
from config import TYPE_CODES, CODE_TO_TYPE, ZONE_CODES, CODE_TO_ZONE, AES_KEY

# Đảm bảo AES_KEY có độ dài hợp lệ (16, 24 hoặc 32 bytes) bằng cách căn phải ljust
_key_len = len(AES_KEY)
if _key_len in [16, 24, 32]:
    VALID_AES_KEY = AES_KEY
elif _key_len < 16:
    VALID_AES_KEY = AES_KEY.ljust(16, b'\x00')
elif _key_len < 24:
    VALID_AES_KEY = AES_KEY.ljust(24, b'\x00')
elif _key_len < 32:
    VALID_AES_KEY = AES_KEY.ljust(32, b'\x00')
else:
    VALID_AES_KEY = AES_KEY[:32]

tx_sequence_counter = 0

def get_next_sequence_number() -> int:
    """Tự động tăng và trả về Sequence Counter cho bản tin tiếp theo"""
    global tx_sequence_counter
    tx_sequence_counter += 1
    return tx_sequence_counter

def aes_ccm_encrypt(zone_id: int, type_code: int, seq_num: int, plaintext: bytes) -> tuple[bytes, bytes]:
    """Mã hóa AES-CCM và trả về (ciphertext, tag)"""
    # Tạo Nonce 13-Byte: [Zone ID (1B)][Type Code (1B)][Seq (4B)] + 7 Bytes 0x00
    nonce = struct.pack(">BBI", zone_id, type_code, seq_num) + b"\x00" * 7
    cipher = AES.new(VALID_AES_KEY, AES.MODE_CCM, nonce=nonce, mac_len=4)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return ciphertext, tag

def aes_ccm_decrypt(zone_id: int, type_code: int, seq_num: int, ciphertext: bytes, tag: bytes) -> bytes:
    """Giải mã AES-CCM và xác thực tính toàn vẹn (trả về plaintext hoặc None)"""
    nonce = struct.pack(">BBI", zone_id, type_code, seq_num) + b"\x00" * 7
    cipher = AES.new(VALID_AES_KEY, AES.MODE_CCM, nonce=nonce, mac_len=4)
    try:
        return cipher.decrypt_and_verify(ciphertext, tag)
    except ValueError:
        return None

def calculate_checksum(zone_id: int, type_code: int, length: int, payload: bytes) -> int:
    """Tính toán XOR Checksum cho khung truyền tin"""
    chk = zone_id ^ type_code ^ length
    for b in payload:
        chk ^= b
    return chk

def wrap_uplink_frame(zone_id: int, type_code: int, payload: bytes) -> str:
    """Đóng gói dữ liệu uplink (Device -> Gateway) thành chuỗi Hex có mã hóa bảo mật AES-CCM"""
    seq_num = get_next_sequence_number()
    ciphertext, tag = aes_ccm_encrypt(zone_id, type_code, seq_num, payload)
    # Secure Payload: [Sequence Number (4B)] + [Ciphertext] + [Tag (4B)]
    secure_payload = struct.pack(">I", seq_num) + ciphertext + tag
    
    length = len(secure_payload)
    checksum = calculate_checksum(zone_id, type_code, length, secure_payload)
    frame = bytearray([0xA5, zone_id, type_code, length]) + secure_payload + bytearray([checksum, 0x5A])
    return frame.hex().upper()

def wrap_downlink_frame(zone_id: int, type_code: int, payload: bytes) -> str:
    """Đóng gói dữ liệu downlink (Gateway -> Device) thành chuỗi Hex có mã hóa AES-CCM (dùng cho test)"""
    seq_num = get_next_sequence_number()
    ciphertext, tag = aes_ccm_encrypt(zone_id, type_code, seq_num, payload)
    secure_payload = struct.pack(">I", seq_num) + ciphertext + tag
    
    length = len(secure_payload)
    checksum = calculate_checksum(zone_id, type_code, length, secure_payload)
    frame = bytearray([0x5A, zone_id, type_code, length]) + secure_payload + bytearray([checksum, 0xA5])
    return frame.hex().upper()

def parse_downlink_frame(hex_str: str):
    """Giải mã khung truyền tin downlink (Gateway -> Device) và giải mã AES-CCM"""
    try:
        hex_clean = hex_str.strip().replace(" ", "")
        data = bytes.fromhex(hex_clean)
        if len(data) < 15: # Ít nhất: 6 bytes overhead + 4B seq + 4B tag + 1B payload
            return None 
        if data[0] != 0x5A or data[-1] != 0xA5:
            return None 
            
        zone_id = data[1]
        type_code = data[2]
        length = data[3]
        
        if len(data) != 6 + length:
            return None 
            
        secure_payload = data[4:4+length]
        checksum = data[4+length]
        
        if checksum != calculate_checksum(zone_id, type_code, length, secure_payload):
            return None 
            
        # Tách Secure Payload: [Seq (4B)] + [Ciphertext] + [Tag (4B)]
        if len(secure_payload) < 8:
            return None
        seq_num = struct.unpack(">I", secure_payload[:4])[0]
        ciphertext = secure_payload[4:-4]
        tag = secure_payload[-4:]
        
        # Giải mã và kiểm tra tính hợp lệ bằng AES-CCM
        plaintext = aes_ccm_decrypt(zone_id, type_code, seq_num, ciphertext, tag)
        if plaintext is None:
            print(f"[SECURITY ALERT] Nhận lệnh Downlink sai mã xác thực AES-CCM! Gói tin bị từ chối.", flush=True)
            return None
            
        return {
            "zone_id": zone_id,
            "type_code": type_code,
            "payload": plaintext
        }
    except Exception:
        return None

# --- BỘ ENCODE TELEMETRY (UPLINK) ---

def encode_dht22(zone_code: int, temp: float, humid: float) -> str:
    """Mã hóa cảm biến nhiệt ẩm DHT22 (4 Bytes)"""
    payload = struct.pack(">hH", int(temp * 10), int(humid * 10))
    return wrap_uplink_frame(zone_code, TYPE_CODES["dht22"], payload)

def encode_mq2(zone_code: int, smoke: bool) -> str:
    """Mã hóa cảm biến báo khói MQ2 (1 Byte)"""
    payload = struct.pack(">B", 1 if smoke else 0)
    return wrap_uplink_frame(zone_code, TYPE_CODES["mq2"], payload)

def encode_lm393(zone_code: int, light_intensity: int) -> str:
    """Mã hóa cảm biến cường độ ánh sáng LM393 (2 Bytes)"""
    payload = struct.pack(">H", int(light_intensity))
    return wrap_uplink_frame(zone_code, TYPE_CODES["lm393"], payload)

def encode_mc38(zone_or_device_code: int, is_open: bool) -> str:
    """Mã hóa cảm biến cửa đóng/mở MC38 (1 Byte)"""
    payload = struct.pack(">B", 1 if is_open else 0)
    return wrap_uplink_frame(zone_or_device_code, TYPE_CODES["mc38"], payload)

def encode_light(zone_code: int, active: bool) -> str:
    """Mã hóa phản hồi trạng thái đèn (1 Byte)"""
    payload = struct.pack(">B", 1 if active else 0)
    return wrap_uplink_frame(zone_code, TYPE_CODES["light"], payload)

def encode_ahu(zone_code: int, active: bool, fan_speed: int, temp_set: float) -> str:
    """Mã hóa phản hồi trạng thái điều hòa AHU (4 Bytes)"""
    payload = struct.pack(">BBh", 1 if active else 0, int(fan_speed), int(temp_set * 10))
    return wrap_uplink_frame(zone_code, TYPE_CODES["ahu"], payload)

def encode_curtain(window_code: int, percentage_cover: int) -> str:
    """Mã hóa phản hồi trạng thái rèm cửa (1 Byte)"""
    payload = struct.pack(">B", int(percentage_cover))
    return wrap_uplink_frame(window_code, TYPE_CODES["curtain"], payload)

# --- BỘ DECODE COMMANDS (DOWNLINK) ---

def decode_command_payload(type_code: int, payload: bytes):
    """Giải mã dữ liệu điều khiển của từng loại thiết bị"""
    try:
        if type_code == TYPE_CODES["light"]:
            # Light payload: 1 Byte (0x00/0x01)
            active = struct.unpack(">B", payload)[0] == 1
            return {"active": active}
            
        elif type_code == TYPE_CODES["ahu"]:
            # AHU payload: 4 Bytes (Active(1B), FanSpeed(1B), TempSet(2B))
            active_val, fan_speed, temp_set_val = struct.unpack(">BBh", payload)
            return {
                "active": active_val == 1,
                "fan_speed": fan_speed,
                "temp_set": temp_set_val / 10.0
            }
            
        elif type_code == TYPE_CODES["curtain"]:
            # Curtain payload: 1 Byte (Percentage 0-100)
            percentage_cover = struct.unpack(">B", payload)[0]
            return {"percentage_cover": percentage_cover}
            
        elif type_code in [TYPE_CODES["dht22"], TYPE_CODES["mq2"], TYPE_CODES["lm393"]]:
            # Lệnh Poll: 1 Byte (0x01)
            is_poll = struct.unpack(">B", payload)[0] == 0x01
            return {"poll": is_poll}
            
    except Exception:
        pass
    return None
