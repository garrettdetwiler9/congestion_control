import socket
import time

PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
MESSAGE_SIZE = PACKET_SIZE - SEQ_ID_SIZE
TIMEOUT = 0.5 

FILE_PATH = f"./file.mp3"
RECEIVER_DEST = ("0.0.0.0", 5001)

def create_packet(seq_id, data):
    return int.to_bytes(seq_id, SEQ_ID_SIZE, signed=True, byteorder='big') + data

def send_packets(FILE_PATH, RECEIVER_DEST):
    
    # open file
    with open(FILE_PATH, 'rb') as f:
        data = f.read()
    
    total_byte_count = len(data)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reno_socket:
        reno_socket.bind(('', 0))
        
        # short socket timeout for non-blocking ACK checks
        reno_socket.settimeout(0.01) 

        overall_start_timestamp = time.time()
        packet_delays = []
        packet_start_times = {}

        # state vars
        base = 0              
        next_seq_num = 0      
        
        # cwnd & ssthresh
        cwnd = MESSAGE_SIZE * 1.0  # starts at 1 pascket size 
        ssthresh = 64 * MESSAGE_SIZE # 64 packet max size
        
        dup_ack_count = 0
        fast_recovery = False
        
        base_timer = time.time()

        # loop until all bytes are ACKed
        while base < total_byte_count:

            # fill window up to cwnd
            while next_seq_num < base + cwnd and next_seq_num < total_byte_count:
                
                payload = data[next_seq_num : next_seq_num + MESSAGE_SIZE]
                packet = create_packet(next_seq_num, payload)
                
                reno_socket.sendto(packet, RECEIVER_DEST)
                
                if next_seq_num not in packet_start_times:
                    packet_start_times[next_seq_num] = time.time()
                
                if base == next_seq_num:
                    base_timer = time.time()

                next_seq_num += len(payload)

            # check for ACKs
            try:
                ack_packet, _ = reno_socket.recvfrom(PACKET_SIZE)
                ack_seq = int.from_bytes(ack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')

                if ack_seq > base: # ACK received
                    
                    # delay metrics calcs
                    current_chk = base
                    while current_chk < ack_seq:
                        if current_chk in packet_start_times:
                            packet_delays.append(time.time() - packet_start_times[current_chk])
                            del packet_start_times[current_chk]
                        current_chk += MESSAGE_SIZE

                    # state mahcine updates
                    if fast_recovery:
                        cwnd = ssthresh
                        fast_recovery = False
                    else:
                        if cwnd < ssthresh:
                            # Slow Start Phase - increase cwnd by 1 MSS/ACK
                            cwnd += MESSAGE_SIZE
                        else:
                            # congestion avoidance - increase cwmd additively
                            cwnd += MESSAGE_SIZE * (MESSAGE_SIZE / cwnd)

                    base = ack_seq
                    dup_ack_count = 0
                    base_timer = time.time()

                elif ack_seq == base: # duplicate ACK received
                    dup_ack_count += 1
                    
                    if dup_ack_count == 3:
                        # fast retransmit
                        ssthresh = max(2 * MESSAGE_SIZE, cwnd / 2)
                        cwnd = ssthresh + 3 * MESSAGE_SIZE
                        fast_recovery = True
                        
                        # only missing packet
                        payload = data[base : base + MESSAGE_SIZE]
                        packet = create_packet(base, payload)
                        reno_socket.sendto(packet, RECEIVER_DEST)
                        
                    elif dup_ack_count > 3:
                        # fast recovery - inflate window for each additional dup ACK
                        cwnd += MESSAGE_SIZE

            except socket.timeout:
                pass
            
            # retransmission after timeout
            if time.time() - base_timer > TIMEOUT:
                # reset to slow start
                ssthresh = max(2 * MESSAGE_SIZE, cwnd / 2)
                cwnd = MESSAGE_SIZE
                dup_ack_count = 0
                fast_recovery = False
                
                # reset next_seq_num to restart sending from lost pkt
                next_seq_num = base
                base_timer = time.time()

        # teardown
        packet = create_packet(base, b'')
        finack_received = False
        
        while not finack_received:
            reno_socket.sendto(packet, RECEIVER_DEST)
            try:
                reno_socket.settimeout(1.0) 
                ack_packet, _ = reno_socket.recvfrom(PACKET_SIZE)
                ack_seq = int.from_bytes(ack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')
                
                if ack_seq == base:
                    finack_packet, _ = reno_socket.recvfrom(PACKET_SIZE)
                    finack_seq = int.from_bytes(finack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')
                    
                    if finack_seq == base + 3:
                        finack_reply = create_packet(0, b'==FINACK==')
                        reno_socket.sendto(finack_reply, RECEIVER_DEST)
                        finack_received = True
            except socket.timeout:
                continue
        
        overall_end_timestamp = time.time()
        total_time = overall_end_timestamp - overall_start_timestamp
    
    # final metrics
    avg_throughput = total_byte_count / total_time
    avg_packet_delay = sum(packet_delays) / len(packet_delays) if packet_delays else 0
    avg_performance = 0.3 * (avg_throughput / 1000) + (0.7 / avg_packet_delay) if avg_packet_delay > 0 else 0

    return avg_throughput, avg_packet_delay, avg_performance

# output
throughput, delay, performance = send_packets(FILE_PATH, RECEIVER_DEST)
print(f"AVG Throughput (bytes/sec): {throughput:.7f}, AVG Packet Delay (sec): {delay:.7f}, AVG Performance Metric: {performance:.7f}")