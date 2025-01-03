import qrcode
from io import BytesIO
import socket
from flask import send_file

def get_local_ip():
    try:
        # Get the local IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def generate_qr_code(port=5000):
    # Get local IP and create URL
    local_ip = get_local_ip()
    network_url = f"http://{local_ip}:{port}"
    
    # Create QR code instance
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    
    # Add the data
    qr.add_data(network_url)
    qr.make(fit=True)

    # Create an image from the QR Code
    qr_image = qr.make_image(fill_color="#007bff", back_color="white")
    
    # Save it to a bytes buffer
    buffer = BytesIO()
    qr_image.save(buffer, format='PNG')
    buffer.seek(0)
    
    return buffer
