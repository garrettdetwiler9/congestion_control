import socket
import time

PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
MESSAGE_SIZE = PACKET_SIZE - SEQ_ID_SIZE
TIMEOUT = 0.5 # Reduced timeout for faster reaction in sliding window
WINDOW_SIZE = 100 # Number of packets in the window

FILE_PATH = f"./file.mp3"
RECEIVER_DEST = ("0.0.0.0", 5001)

def create_packet(seq_id, data):
    return int.to_bytes(seq_id, SEQ_ID_SIZE, signed=True, byteorder='big') + data

def send_packets(FILE_PATH, RECEIVER_DEST):
    
    # opens the file
    with open(FILE_PATH, 'rb') as f:
        data = f.read()
    
    total_byte_count = len(data)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.bind(('', 0))
        
        # Set a short socket timeout to allow non-blocking checks for ACKs
        # so we can keep sending packets while waiting
        udp_socket.settimeout(0.01) 

        overall_start_timestamp = time.time()
        packet_delays = []
        
        # Sliding Window State Variables
        base = 0              # The beginning of the window (oldest unacked packet)
        next_seq_num = 0      # The next sequence number to send
        window_size_bytes = WINDOW_SIZE * MESSAGE_SIZE
        
        # Track when the window base was sent to handle timeouts
        base_timer = time.time()
        
        # Map to track start times of packets for delay metrics
        # (Only track the *first* send time for accuracy)
        packet_start_times = {}

        # Loop until all bytes are acknowledged
        while base < total_byte_count:

            # 1. SENDING: Fill window
            # Send packets while we have space in the window and data left to send
            while next_seq_num < base + window_size_bytes and next_seq_num < total_byte_count:
                
                # Create the packet
                payload = data[next_seq_num : next_seq_num + MESSAGE_SIZE]
                packet = create_packet(next_seq_num, payload)
                
                # Send the packet
                udp_socket.sendto(packet, RECEIVER_DEST)
                
                # Metric tracking: Only record start time if it's the first attempt
                if next_seq_num not in packet_start_times:
                    packet_start_times[next_seq_num] = time.time()
                
                # If this is the first packet in the window, start the timer
                if base == next_seq_num:
                    base_timer = time.time()

                next_seq_num += len(payload)

            # 2. RECEIVING: Check for ACKs
            try:
                ack_packet, _ = udp_socket.recvfrom(PACKET_SIZE)
                ack_seq = int.from_bytes(ack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')

                # Cumulative ACK handling
                # If ack_seq > base, receiver has successfully received everything up to ack_seq
                if ack_seq > base:
                    # Calculate delay for all newly acknowledged packets
                    # We iterate through the "gaps" to capture metrics for every packet covered by this cumulative ACK
                    current_chk = base
                    while current_chk < ack_seq:
                        if current_chk in packet_start_times:
                            packet_delays.append(time.time() - packet_start_times[current_chk])
                            del packet_start_times[current_chk] # Clean up memory
                        current_chk += MESSAGE_SIZE

                    # Slide window forward
                    base = ack_seq
                    
                    # Reset timer because window moved
                    base_timer = time.time()

            except socket.timeout:
                # No ACK received in this short interval; continue to checking logic
                pass
            
            # 3. TIMEOUT HANDLING (Go-Back-N)
            # If oldest unACKed packet (base) has timed out, resend whole window
            if time.time() - base_timer > TIMEOUT:
                # Reset next_seq_num to base causes the 'SENDING STEP' loop to re-send everything
                next_seq_num = base
                base_timer = time.time() # Reset timer to avoid immediate consecutive timeouts

        # TEARDOWN
        packet = create_packet(base, b'') # base should now be total_byte_count
        finack_received = False
        
        while not finack_received:
            udp_socket.sendto(packet, RECEIVER_DEST)
            try:
                udp_socket.settimeout(1.0) # Longer timeout for handshake
                ack_packet, _ = udp_socket.recvfrom(PACKET_SIZE)
                ack_seq = int.from_bytes(ack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')
                
                if ack_seq == base:
                    finack_packet, _ = udp_socket.recvfrom(PACKET_SIZE)
                    finack_seq = int.from_bytes(finack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')
                    
                    if finack_seq == base + 3:
                        finack_reply = create_packet(0, b'==FINACK==')
                        udp_socket.sendto(finack_reply, RECEIVER_DEST)
                        finack_received = True
            except socket.timeout:
                continue
        
        overall_end_timestamp = time.time()
        total_time = overall_end_timestamp - overall_start_timestamp
    
    # Calculate metrics
    avg_throughput = total_byte_count / total_time
    avg_packet_delay = sum(packet_delays) / len(packet_delays) if packet_delays else 0
    avg_performance = 0.3 * (avg_throughput / 1000) + (0.7 / avg_packet_delay) if avg_packet_delay > 0 else 0

    return avg_throughput, avg_packet_delay, avg_performance

# output results
throughput, delay, performance = send_packets(FILE_PATH, RECEIVER_DEST)
print(f"AVG Throughput (bytes/sec): {throughput:.7f}, AVG Packet Delay (sec): {delay:.7f}, AVG Performance Metric: {performance:.7f}")