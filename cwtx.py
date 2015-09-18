#! /usr/bin/env python

# Import CW to WAV modules
import sys, math, audiodev

# Import Gnuradio modules
from gnuradio import analog
from gnuradio import blocks
from gnuradio import filter
from gnuradio import gr
from gnuradio.filter import firdes
import osmosdr

# Default constants
DEF_SAMPLE_RATE = 22050
DEF_MORSE_FREQ = 433000000 # MHz
DEF_AMPLITUDE = 30000 # 0-32767
DEF_WORDS_PER_MIN = 25
DEF_LETTER_SPACING = 100 # Percent

# How many samples to spend ramping up or down
RAMP_SAMPLE_PERCENT = .075 # = 7.5%

# Globals
global morse_freq_hz
global sample_rate
global amplitude
global words_per_min
global letter_spacing

morsetab = {
		'A': '.-',				
		'B': '-...',
		'C': '-.-.',
		'D': '-..',
		'E': '.',
		'F': '..-.',
		'G': '--.',
		'H': '....',
		'I': '..',
		'J': '.---',
		'K': '-.-',
		'L': '.-..',
		'M': '--',
		'N': '-.',
		'O': '---',
		'P': '.--.',
		'Q': '--.-',
		'R': '.-.',
		'S': '...',
		'T': '-',
		'U': '..-',
		'V': '...-',
		'W': '.--',
		'X': '-..-',
		'Y': '-.--',
		'Z': '--..',
		'0': '-----',			
		'1': '.----',
		'2': '..---',			
		'3': '...--',			
		'4': '....-',			
		'5': '.....',			
		'6': '-....',			
		'7': '--...',			
		'8': '---..',			
		'9': '----.',			
		',': '--..--',
		'.': '.-.-.-',
		'?': '..--..',
		';': '-.-.-.',
		':': '---...',
		"'": '.----.',
		'-': '-....-',	
		'/': '-..-.',
		'(': '-.--.-',
		')': '-.--.-',
		'_': '..--.-',
		' ': ' '			
}

def main():
	import wave

	dev = None
	morse_freq_hz = DEF_MORSE_FREQ / 1000000
	sample_rate = DEF_SAMPLE_RATE
	amplitude = DEF_AMPLITUDE
	words_per_min = DEF_WORDS_PER_MIN
	letter_spacing = DEF_LETTER_SPACING
	dev = wave.open('/tmp/morse.wav', 'w')

	# Get the words to be converted either from command line or stdin
	source = raw_input("Enter your text: ").upper()
	source += ("   ")


	# Set file/dev sample rate & parameters
	dev.setparams((1, 2, sample_rate, 0, 'NONE', 'not compressed'))

	# Calculate speed of morse based on WPM (Dot Time = 1200 / WPM)
	dot_msecs =  1200 / words_per_min # Time in msecs a dot should take (25 wpm = 48 msecs)
	dot_samples = int( float(dot_msecs) / 1000 * sample_rate )
	dah_samples = 3 * dot_samples
		
	# CD - add space in front (time for squelch to open?) of 0.5s
	pause(dev, sample_rate / 2)

	# Play out morse
	for line in source:
		mline, vmline = morse(line)
		play(mline, dev, morse_freq_hz, amplitude, sample_rate, dot_samples, dah_samples, letter_spacing)
		if hasattr(dev, 'wait'):
			dev.wait()

	dev.close()
	
	tb = cw_tx()
	tb.start()
	tb.wait()

# Convert a string to morse code with \001 between the characters in the string.
def morse(line):
	vres = res = ''
	for c in line:
		try:
			res += morsetab[c] + '\001'
			vres += morsetab[c] + ' '
		except KeyError:
			pass
	return res, vres

# Play a line of morse code.
def play(line, dev, morse_freq_hz, amplitude, sample_rate, dot_samples, dah_samples, letter_spacing):
	ramp_samples = int( dot_samples * RAMP_SAMPLE_PERCENT )
	dot_bytes = sinusodial(dev, morse_freq_hz, amplitude, sample_rate, dot_samples, ramp_samples)
	dah_bytes = sinusodial(dev, morse_freq_hz, amplitude, sample_rate, dah_samples, ramp_samples)
	for c in line:
		if c == '.':
			dev.writeframesraw( dot_bytes )
		elif c == '-':
			dev.writeframesraw( dah_bytes )
		else:					# space
			pause(dev, int ( ( dah_samples + dot_samples ) * letter_spacing / 100 ) )
		pause(dev, dot_samples)

def sinusodial(dev, morse_freq_hz, amplitude, sample_rate, length, ramp_samples):
	
	# Add in ramp up/down of sinusodial wave to avoid clicks
	# This also means using cos instead of sine to allow smother ramping start/stop points

	res = ''
	sample = 0

	# Calculate the amount we need to increase pi for each sample
	radian_inc = 2 * math.pi * morse_freq_hz 
	
	# Ramp up
	for i in range(ramp_samples):
		val = int(math.cos(radian_inc * sample / sample_rate ) * amplitude * i / ramp_samples )
		res += chr(val & 255) + chr((val >> 8) & 255)
		sample += 1

	# Full amplitude
	for i in range(length - ramp_samples * 2):
		val = int(math.cos(radian_inc * sample / sample_rate ) * amplitude )
		res += chr(val & 255) + chr((val >> 8) & 255)
		sample += 1

	# Ramp down
	for i in range(ramp_samples):
		val = int(math.cos(radian_inc * sample / sample_rate ) * amplitude * (ramp_samples - i) / ramp_samples )
		res += chr(val & 255) + chr((val >> 8) & 255) 
		sample += 1

	return res


def pause(dev, length):
	dev.writeframesraw('\0' * length * 2) # * 2 bytes p/sample


class cw_tx(gr.top_block):

    def __init__(self):

        gr.top_block.__init__(self, "CW Tx")

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 2e6

        ##################################################
        # Blocks
        ##################################################
        self.rational_resampler_xxx_0 = filter.rational_resampler_ccc(
                interpolation=int(samp_rate),
                decimation=176400,
                taps=None,
                fractional_bw=None,
        )
        self.osmosdr_sink_0 = osmosdr.sink( args="numchan=" + str(1) + " " + "" )
        self.osmosdr_sink_0.set_sample_rate(samp_rate)
        self.osmosdr_sink_0.set_center_freq(DEF_MORSE_FREQ, 0)
        self.osmosdr_sink_0.set_freq_corr(0, 0)
        self.osmosdr_sink_0.set_gain(10, 0)
        self.osmosdr_sink_0.set_if_gain(20, 0)
        self.osmosdr_sink_0.set_bb_gain(20, 0)
        self.osmosdr_sink_0.set_antenna("", 0)
        self.osmosdr_sink_0.set_bandwidth(0, 0)
          
        self.blocks_wavfile_source_0 = blocks.wavfile_source("/tmp/morse.wav", False)
        self.analog_wfm_tx_0 = analog.wfm_tx(
        	audio_rate=DEF_SAMPLE_RATE,
        	quad_rate=176400,
        	tau=75e-6,
        	max_dev=5e3,
        )

        ##################################################
        # Connections
        ##################################################
        self.connect((self.blocks_wavfile_source_0, 0), (self.analog_wfm_tx_0, 0))    
        self.connect((self.analog_wfm_tx_0, 0), (self.rational_resampler_xxx_0, 0))    
        self.connect((self.rational_resampler_xxx_0, 0), (self.osmosdr_sink_0, 0))    
 

if __name__ == '__main__':
	main()
	while True:
	    main()
