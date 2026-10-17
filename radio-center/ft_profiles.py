"""Receive dial frequencies (Hz), HF amateur bands and RTL-SDR v3 input modes."""
BANDS={
 '160m':(1800000,2000000,1840000,1840000),
 '80m':(3500000,3800000,3573000,3575000),
 '60m':(5351500,5366500,5357000,5357000),
 '40m':(7000000,7200000,7074000,7047500),
 '30m':(10100000,10150000,10136000,10140000),
 '20m':(14000000,14350000,14074000,14080000),
 '17m':(18068000,18168000,18100000,18104000),
 '15m':(21000000,21450000,21074000,21140000),
 '12m':(24890000,24990000,24915000,24919000),
 '10m':(28000000,29700000,28074000,28180000),
 '2m':(144000000,146000000,144174000,144170000),
 '70cm':(430000000,440000000,432174000,432170000),
}
PROFILES={f'{band}-{mode}':(limits[2 if mode=='ft8' else 3],15 if mode=='ft8' else 7.5,mode,band) for band,limits in BANDS.items() for mode in ('ft8','ft4')}
def metadata():
 return {key:dict(frequency=p[0],mode=p[2],band=p[3],min=BANDS[p[3]][0],max=BANDS[p[3]][1],direct=p[0]<24000000,nonstandard=p[2]=='ft4' and p[3] in ('160m','60m')) for key,p in PROFILES.items()}
def validate_frequency(profile,frequency):
 if profile not in PROFILES or isinstance(frequency,bool) or not isinstance(frequency,int):raise ValueError('Neplatná frekvence')
 band=PROFILES[profile][3];lo,hi,*_=BANDS[band]
 if not lo<=frequency<=hi-4000:raise ValueError('Frekvence musí být uvnitř vybraného pásma s rezervou pro USB signál')
 return frequency

MSK_PROFILES={'2m-msk144':(144360000,15,'msk144','2m'),'70cm-msk144':(432370000,15,'msk144','70cm')}
def msk_metadata():
 return {key:dict(frequency=p[0],mode=p[2],band=p[3],min=BANDS[p[3]][0],max=BANDS[p[3]][1],direct=False,nonstandard=False) for key,p in MSK_PROFILES.items()}
def validate_msk_frequency(profile,frequency):
 if profile not in MSK_PROFILES or isinstance(frequency,bool) or not isinstance(frequency,int):raise ValueError('Neplatná frekvence')
 lo,hi,*_=BANDS[MSK_PROFILES[profile][3]]
 if not lo<=frequency<=hi-4000:raise ValueError('Frekvence mimo vybrané pásmo')
 return frequency
