"""Read-only OpenWebRX tuning snapshot; contains no client identities."""
def value(props,key,default=None):
 return props[key] if key in props else default

def snapshot(registry=None,sources=None):
 if registry is None:
  from owrx.client import ClientRegistry
  registry=ClientRegistry.getSharedInstance()
 if sources is None:
  from owrx.sdr import SdrService
  sources=SdrService.getActiveSources().values()
 receivers=[];listeners=[]
 for source in tuple(sources):
  try:
   props=source.getProps()
   receivers.append({'receiver':source.getName(),'profile':source.getProfileName(),'center_frequency':value(props,'center_freq'),'sample_rate':value(props,'samp_rate')})
  except (KeyError,AttributeError,RuntimeError):continue
 for client in tuple(registry.clients):
  try:
   source=client.sdr;dsp=client.dsp
   if source is None or dsp is None:continue
   props=dsp.props;center=value(props,'center_freq');offset=value(props,'offset_freq')
   frequency=center+offset if center is not None and offset is not None else value(props,'start_freq')
   low=value(props,'low_cut');high=value(props,'high_cut')
   listeners.append({'receiver':source.getName(),'profile':source.getProfileName(),'frequency':frequency,'modulation':value(props,'mod',value(props,'start_mod')),'secondary_modulation':value(props,'secondary_mod'),'bandwidth':high-low if low is not None and high is not None else None})
  except (KeyError,AttributeError,TypeError,RuntimeError):continue
 return {'receivers':receivers,'listeners':listeners}
