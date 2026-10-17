#!/usr/bin/python3
"""Build the upstream MAP65 file decoder without Qt, a desktop or transmit code."""
import hashlib,json,re,shutil,subprocess,sys,tarfile,urllib.request
from pathlib import Path
BASE=Path(__file__).resolve().parent
WORK=Path(sys.argv[1] if len(sys.argv)>1 else BASE/'build-work').resolve()
WORK.mkdir(parents=True,exist_ok=True)
archive=WORK/'wsjtx-v2.7.0.tar.gz'
if not archive.exists():urllib.request.urlretrieve('https://codeload.github.com/WSJTX/wsjtx/tar.gz/refs/tags/v2.7.0',archive)
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='6c7a0f76dcdd22238c514143c23910a6089693fb40b8c3bb5602a64a4a5ce0c5','Unexpected upstream archive'
print('WSJT-X v2.7.0 archive SHA256:',hashlib.sha256(archive.read_bytes()).hexdigest(),flush=True)
with tarfile.open(archive) as t:t.extractall(WORK,filter='data')
src=WORK/'wsjtx-2.7.0';main=(src/'CMakeLists.txt').read_text();m65=(src/'map65/libm65/CMakeLists.txt').read_text()
def block(text,name):
 match=re.search(r'set\s*\('+name+r'\s+(.*?)\n\s*\)',text,re.S);assert match,name
 return '\n'.join(line.split('#',1)[0] for line in match[1].splitlines()).split()
def paths(names):return [str(src/name) for name in names if not name.startswith('${')]
fort=paths(block(main,'wsjt_FSRCS'))
cs=[]
for name in ('ka9q_CSRCS','qra_CSRCS','wsjt_CSRCS'):cs+=paths(block(main,name))
cs=list(dict.fromkeys(cs))
mapfort=paths(['map65/libm65/'+f for f in block(m65,'libm65_FSRCS') if f not in ('jt65code.f90',)])
mapc=paths(['map65/libm65/'+f for f in ('decode_rs.c','encode_rs.c','init_rs.c','ftrsd2.c','igray.c','wrapkarn.c')])
# Keep the decoder and file reader; replace only hardcoded test station/band
# settings in the upstream command-line driver. Never link m65a/shared memory.
s=(src/'map65/libm65/m65.f90').read_text()
s=s.replace('if(nargs.ne.1 .and. nargs.lt.5) then','if(nargs.ne.9) then')
s=s.replace("     call m65a", "     stop 'Shared-memory/GUI mode disabled'")
s=s.replace('ifile1=5','ifile1=9')
start=s.index('! Some default parameters');end=s.index("  call ftninit('.')",start)
s=s[:start]+'''  call getarg(5,mycall)
  call getarg(6,mygrid)
  hiscall=' '
  hisgrid=' '
  call getarg(7,arg)
  read(arg,*) nfa
  call getarg(8,arg)
  read(arg,*) nfb
  ndepth=2
  neme=0
  ntol=100
  nkeep=1
  mcall3=0
  mousefqso=(nfa+nfb)/2
  mousedf=0
  nfcal=0
  nrxlog=0
  nxant=0
  max_drift=20
  ndop00=0
  nsave=0
  nfshift=0
  nagain=0
  idphi=0
  datetime=' '
'''+s[end:]
s=s.replace('     read(10) fcenter','     read(10) fcenter\n     nkhz_center=nint(1000.d0*(fcenter-int(fcenter)))')
# Decode once at the final boundary; skip the early extra decode in offline use.
s=s.replace('           if(nhsym.eq.nhsym1) call decode0(dd,ss,savg,nstandalone)','')
s=s.replace('  use timer_module, only: timer','  use wideband_sync, only: get_candidates,candidate\n  use timer_module, only: timer',1)
s=s.replace('  integer*2 i2(NREAD)','  type(candidate) :: eme_cand(50)\n  integer eme_ncand,eme_i\n  integer*2 i2(NREAD)',1)
s=s.replace('  character*80 arg,infile','  character*80 arg,infile\n  character*5 jmodes,qmodes\n  integer npasses,ipass\n  real pass_start,pass_end')
s=s.replace('  call getarg(1,arg)','  call getarg(1,arg)\n  jmodes=arg',1).replace('  call getarg(2,arg)','  call getarg(2,arg)\n  qmodes=arg\n  npasses=max(len_trim(jmodes),len_trim(qmodes))',1)
s=s.replace('              call decode0(dd,ss,savg,nstandalone)', '''              if(scan(jmodes,'ABC').gt.0) then
              call get_candidates(ss,savg,.false.,nhsym,nfa-nkhz_center+48,nfb-nkhz_center+48,2,2,eme_cand,eme_ncand)
              do eme_i=1,eme_ncand
                 if(eme_cand(eme_i)%iflip.ne.0) then
                    write(*,*) 'EME_JT_CANDIDATE ',real(int(fcenter),8)*1.d6+1000.d0*(eme_cand(eme_i)%f+nkhz_center-48),eme_cand(eme_i)%snr
                 endif
              enddo
              call flush(6)
              endif
              do ipass=1,npasses
                 n=0
                 m=0
                 if(jmodes(ipass:ipass).eq.'A') n=1
                 if(jmodes(ipass:ipass).eq.'B') n=2
                 if(jmodes(ipass:ipass).eq.'C') n=3
                 if(qmodes(ipass:ipass).ge.'A'.and.qmodes(ipass:ipass).le.'E') m=ichar(qmodes(ipass:ipass))-ichar('A')+1
                 nmode=10*m
! JT65 is routed to the installed WSJT-X jt9 decoder by the receive adapter.
                 newdat=1
                 call cpu_time(pass_start)
                 write(*,*) 'EME_PASS_START ',jmodes(ipass:ipass),qmodes(ipass:ipass)
                 call flush(6)
                 if(m.gt.0) call decode0(dd,ss,savg,nstandalone)
                 call cpu_time(pass_end)
                 write(*,*) 'EME_PASS_DONE ',jmodes(ipass:ipass),qmodes(ipass:ipass),pass_end-pass_start
                 call flush(6)
              enddo''')
(WORK/'eme_m65.f90').write_text(s)
cm='''cmake_minimum_required(VERSION 3.18)
project(eme_native LANGUAGES C Fortran)
add_compile_definitions(BIGSYM=1)
set(CMAKE_Fortran_FLAGS "-O2 -fallow-argument-mismatch -ffree-line-length-none -fno-align-commons")
include_directories("'''+str(src/'lib')+'" "'+str(src/'map65/libm65')+'''" /usr/include)
set(CMAKE_Fortran_MODULE_DIRECTORY ${CMAKE_BINARY_DIR}/mod)
include_directories(${CMAKE_Fortran_MODULE_DIRECTORY})
'''
cm+='set_source_files_properties("'+str(src/'lib/types.f90')+'" "'+str(src/'lib/C_interface_module.f90')+'" PROPERTIES COMPILE_OPTIONS "-O0")\n'
cm+='add_library(common STATIC\n'+'\n'.join(fort+cs)+'\n)\n'
cm+='add_library(mapcore STATIC\n'+'\n'.join(mapfort+mapc)+'\n)\n'
cm+='set_target_properties(mapcore PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_BINARY_DIR}/mapmod)\ntarget_include_directories(mapcore BEFORE PRIVATE ${CMAKE_BINARY_DIR}/mapmod)\nadd_dependencies(mapcore common)\ntarget_link_libraries(mapcore common fftw3f_threads fftw3f fftw3 m pthread)\n'
cm+='add_executable(eme-m65 eme_m65.f90)\ntarget_include_directories(eme-m65 BEFORE PRIVATE ${CMAKE_BINARY_DIR}/mapmod)\ntarget_link_libraries(eme-m65 mapcore)\n'
cm+='add_executable(eme-mapsim '+str(src/'map65/libm65/mapsim.f90')+')\ntarget_link_libraries(eme-mapsim mapcore)\n'
(WORK/'CMakeLists.txt').write_text(cm)
subprocess.run(['cmake','-S',str(WORK),'-B',str(WORK/'build'),'-G','Ninja','-DCMAKE_Fortran_COMPILER=/usr/bin/gfortran-13','-DCMAKE_C_COMPILER=/usr/bin/gcc-13'],check=True)
subprocess.run(['cmake','--build',str(WORK/'build'),'-j','2'],check=True)

shutil.copy2(WORK/'build/eme-m65',BASE/'eme-m65')
shutil.copy2(src/'COPYING',BASE/'COPYING')
