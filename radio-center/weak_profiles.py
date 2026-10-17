"""Receive-only Q65/JT65 profiles; dial frequencies can be changed in the UI."""
from ft_profiles import BANDS
HF_JT65={'160m':1838000,'80m':3576000,'40m':7076000,'30m':10138000,'20m':14076000,'17m':18102000,'15m':21076000,'12m':24917000,'10m':28076000}
PROFILES={}
for band,freq in (('2m',144170000),('70cm',432065000)):
 for period,sub in ((60,'A'),(60,'B'),(30,'A'),(30,'B'),(15,'A'),(15,'B'),(120,'A'),(120,'B'),(300,'A'),(300,'B')):
  mode=f'q65-{period}{sub.lower()}';PROFILES[f'{band}-{mode}']=(freq,period,mode,band)
for band,freq in HF_JT65.items():PROFILES[f'{band}-jt65a']=(freq,60,'jt65a',band)
for band,freq,subs in (('2m',144120000,'AB'),('70cm',432065000,'BC')):
 for sub in subs:
  mode='jt65'+sub.lower();PROFILES[f'{band}-{mode}']=(freq,60,mode,band)
def metadata():
 return {key:dict(frequency=p[0],period=p[1],mode=p[2],band=p[3],min=BANDS[p[3]][0],max=BANDS[p[3]][1],direct=p[0]<24000000,nonstandard=False,manual=p[3] in ('2m','70cm')) for key,p in PROFILES.items()}
def validate_frequency(profile,frequency):
 if profile not in PROFILES or isinstance(frequency,bool) or not isinstance(frequency,int):raise ValueError('Neplatná frekvence nebo režim')
 lo,hi,*_=BANDS[PROFILES[profile][3]]
 if not lo<=frequency<=hi-4000:raise ValueError('Frekvence musí být uvnitř pásma s rezervou 4 kHz pro USB')
 return frequency
