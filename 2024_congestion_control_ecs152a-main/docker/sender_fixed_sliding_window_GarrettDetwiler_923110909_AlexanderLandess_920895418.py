import socket
import time

PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
MESSAGE_SIZE = PACKET_SIZE - SEQ_ID_SIZE
TIMEOUT = 0.5 
WINDOW_SIZE = 100 

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
        
        # short timeout size for recovery
        udp_socket.settimeout(0.01) 

        overall_start_timestamp = time.time()
        packet_delays = []
        
        # state vars
        base = 0              # beginning of window (oldest pkt)
        next_seq_num = 0      # next sequence num to send
        window_size_bytes = WINDOW_SIZE * MESSAGE_SIZE # window size... duh
        
        # timer for when window base sent
        base_timer = time.time()
        
        packet_start_times = {}

        #loop until all bytes are ACKed
        while base < total_byte_count:

            # fill window
            # send packets while space in window and data left to send
            while next_seq_num < base + window_size_bytes and next_seq_num < total_byte_count:
                
                # create packet
                payload = data[next_seq_num : next_seq_num + MESSAGE_SIZE]
                packet = create_packet(next_seq_num, payload)
                
                # send packet
                udp_socket.sendto(packet, RECEIVER_DEST)
                
                # record start time if first attempt
                if next_seq_num not in packet_start_times:
                    packet_start_times[next_seq_num] = time.time()
                
                # if first packet in window --> start timer
                if base == next_seq_num:
                    base_timer = time.time()

                next_seq_num += len(payload)

            # check for ACKs
            try:
                ack_packet, _ = udp_socket.recvfrom(PACKET_SIZE)
                ack_seq = int.from_bytes(ack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')

                # if ack_seq > base, receiver successfully received window up to ack_seq
                if ack_seq > base:
                    # calculate delay for all newly ACKed packets
                    # iter through the packet gaps to get metrics
                    current_chk = base
                    while current_chk < ack_seq:
                        if current_chk in packet_start_times:
                            packet_delays.append(time.time() - packet_start_times[current_chk])
                            del packet_start_times[current_chk] 
                        current_chk += MESSAGE_SIZE

                    # move window forward
                    base = ack_seq
                    
                    # reset timer because window moved
                    base_timer = time.time()

            except socket.timeout:
                # no ACK received right now--> continue 
                pass
            
            # Go-Back-N
            # if oldest unACKed packet (base) has timed out, resend whole window
            if time.time() - base_timer > TIMEOUT:
                # reset next_seq_num to base in order to re-send everything
                next_seq_num = base
                base_timer = time.time() # reset timer 

        # teardown
        packet = create_packet(base, b'') # base should now be total_byte_count
        finack_received = False
        
        while not finack_received:
            udp_socket.sendto(packet, RECEIVER_DEST)
            try:
                udp_socket.settimeout(1.0) # longer temp timeout
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
    
    # metrics
    avg_throughput = total_byte_count / total_time
    avg_packet_delay = sum(packet_delays) / len(packet_delays) if packet_delays else 0
    avg_performance = 0.3 * (avg_throughput / 1000) + (0.7 / avg_packet_delay) if avg_packet_delay > 0 else 0

    return avg_throughput, avg_packet_delay, avg_performance

# output
throughput, delay, performance = send_packets(FILE_PATH, RECEIVER_DEST)
print(f"{throughput:.7f}, {delay:.7f}, {performance:.7f}")