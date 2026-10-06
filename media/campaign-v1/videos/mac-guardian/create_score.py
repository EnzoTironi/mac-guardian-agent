"""Original 144 BPM instrumental score. Run with: uv run --with numpy create_score.py."""
from pathlib import Path
import wave
import numpy as np

ROOT=Path(__file__).resolve().parent
SR=48000
DURATION=40
BEAT=60/144
N=SR*DURATION
rng=np.random.default_rng(43119)
mix=np.zeros((N,2),dtype=np.float64)

def note(n):
    return 440*2**((n-69)/12)

def put(start,sound,gain=1,pan=0):
    pos=int(start*SR)
    if pos<0:
        sound=sound[-pos:];pos=0
    length=min(len(sound),N-pos)
    if length<=0:return
    mix[pos:pos+length,0]+=sound[:length]*gain*np.sqrt((1-pan)/2)
    mix[pos:pos+length,1]+=sound[:length]*gain*np.sqrt((1+pan)/2)

def tone(freq,length,attack=.01,decay=2.5):
    t=np.arange(int(length*SR))/SR
    env=np.minimum(1,t/attack)*np.exp(-decay*t)
    return (.78*np.sin(2*np.pi*freq*t)+.16*np.sin(2*np.pi*freq*2*t)+.06*np.sin(2*np.pi*freq*3*t))*env

def kick():
    t=np.arange(int(.5*SR))/SR
    phase=2*np.pi*(48*t+52*(1-np.exp(-26*t))/26)
    return np.sin(phase)*np.exp(-11*t)+rng.normal(0,.07,len(t))*np.exp(-140*t)

def snare():
    t=np.arange(int(.22*SR))/SR
    noise=rng.normal(0,1,len(t));noise=np.diff(np.r_[0,noise])
    return noise*np.exp(-23*t)*.15+np.sin(2*np.pi*176*t)*np.exp(-35*t)*.18

def hat(length=.07):
    t=np.arange(int(length*SR))/SR
    noise=rng.normal(0,1,len(t));noise=np.diff(np.r_[0,noise])
    return noise*np.exp(-70*t)*.08

def sweep(length=1.0):
    t=np.arange(int(length*SR))/SR
    noise=rng.normal(0,1,len(t))
    smooth=np.convolve(noise,np.ones(12)/12,mode='same')
    env=np.sin(np.pi*t/length)**2
    return (noise-smooth)*env*.09

# Warm sustained A minor pads; no stock music, models or external recordings.
progression=[[57,60,64],[53,57,60],[55,59,62],[57,60,64]]
for bar in range(12):
    start=bar*8*BEAT
    chord=progression[(bar//2)%4]
    length=min(8*BEAT+1,DURATION-start)
    t=np.arange(int(length*SR))/SR
    env=np.minimum(1,t/.45)*np.minimum(1,np.maximum(0,length-t)/.8)
    for j,n in enumerate(chord):
        carrier=np.sin(2*np.pi*note(n)*t)+.28*np.sin(2*np.pi*note(n)*1.003*t)
        put(start,carrier*env,.055,[-.6,0,.6][j])

for beat in range(96):
    at=beat*BEAT
    block=int(beat//16)
    bass=[33,33,29,31,33,33][block]
    # Beginning resembles a physician's pulse; the rhythm then becomes a score.
    if beat<12:
        if beat%3==0:
            put(at,kick(),.44);put(at+.18,kick(),.25)
    elif beat<80:
        put(at,kick(),.58)
        if beat%4 in (1,3):put(at,snare(),.8)
        put(at,hat(),.55,-.3)
        put(at+BEAT/2,hat(),.32,.35)
    else:
        if beat%2==0:put(at,kick(),.42)
        if beat%4==3:put(at,snare(),.48)
    if beat>=12:
        put(at,tone(note(bass),.36,decay=5),.23)
    if beat>=8 and beat<88:
        pitches=[69,76,72,76,69,79,76,72]
        for half in range(2):
            k=(beat*2+half)%8
            put(at+half*BEAT/2,tone(note(pitches[k]),.48,decay=8),.055,(-.4 if half==0 else .4))

# Emphasize scene boundaries, with a clean rise into each cut.
cuts=[5,10,16.666667,23.333333,28.333333,33.333333]
for cut in cuts:
    put(cut-.65,sweep(.65),.5,.05)
    put(cut,tone(42,.95,decay=7),.45)
    put(cut,sweep(.45),.48,-.1)

# A single bright resolve on the final identity card.
for n in [69,72,76,81]:put(33.333333,tone(note(n),4,attack=.02,decay=.85),.06)

# Stereo delay, controlled saturation and purposeful final fade.
delay=int(.15*SR)
mix[delay:,0]+=mix[:-delay,1]*.075
mix[delay:,1]+=mix[:-delay,0]*.075
mix=np.tanh(mix*1.2)
fade=np.ones(N);fade[:int(.025*SR)]=np.linspace(0,1,int(.025*SR));fade[-int(1.1*SR):]=np.linspace(1,0,int(1.1*SR))
mix*=fade[:,None]
mix*=.89/max(.89,np.max(np.abs(mix)))
pcm=(mix*32767).astype('<i2')
out=ROOT/'assets/original-score.wav'
with wave.open(str(out),'wb') as w:
    w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes(pcm.tobytes())
print(f'Original soundtrack: {DURATION}s, {SR} Hz stereo, 144 BPM.')
