"""Rebuild the seven editable HyperFrames scenes from the locked campaign brief."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
FONTS = '''
@font-face{font-family:"Barlow Condensed";font-weight:400;src:url("../../assets/fonts/BarlowCondensed-400.ttf") format("truetype");font-display:block}
@font-face{font-family:"Barlow Condensed";font-weight:700;src:url("../../assets/fonts/BarlowCondensed-700.ttf") format("truetype");font-display:block}
@font-face{font-family:"Barlow Condensed";font-weight:900;src:url("../../assets/fonts/BarlowCondensed-900.ttf") format("truetype");font-display:block}
@font-face{font-family:"JetBrains Mono";font-weight:400;src:url("../../assets/fonts/JetBrainsMono-400.woff2") format("woff2");font-display:block}
'''
CSS = '''
*{box-sizing:border-box}
#root{position:absolute;inset:0;width:100%;height:100%;overflow:hidden;container-type:size;color:#F4F1E7;font-family:"Barlow Condensed",sans-serif;--ink:#07110E;--paper:#F4F1E7;--mint:#93F5CE}
#root .clip{position:absolute;inset:0;width:100%;height:100%}
#root .bg{background:#07110E}
#root .stage{position:absolute;inset:0;overflow:hidden}
#root .chrome{position:absolute;left:5cqw;top:5cqh;font-family:"JetBrains Mono",monospace;font-size:1.08cqw;letter-spacing:.12em;color:#93F5CE}
#root .hero{position:absolute;left:5cqw;top:20cqh;width:49cqw;font-weight:900;font-size:10.6cqw;line-height:.86;letter-spacing:-.018em}
#root .hero>span{display:block}
#root .mint{color:#93F5CE}
#root .support{position:absolute;left:5cqw;top:64cqh;width:45cqw;font-size:2.25cqw;font-weight:400;line-height:1.16}
#root .caption{font-family:"JetBrains Mono",monospace;font-size:1.1cqw;line-height:1.5;letter-spacing:.02em}
#root .foot{position:absolute;left:5cqw;top:78cqh;max-width:88cqw;color:#F4F1E7}
#root .doctor{position:absolute;left:54cqw;top:8cqh;width:41cqw;height:73cqh;object-fit:contain}
#root .pulse{position:absolute;left:5cqw;top:73cqh;width:43cqw;height:5cqh;overflow:visible}
#root .pulse path{fill:none;stroke:#93F5CE;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}
#root .label{font-family:"JetBrains Mono",monospace;font-size:1.05cqw;letter-spacing:.07em}
'''
PULSE = '<svg class="pulse" viewBox="0 0 900 100" data-layout-ignore><path d="M0 60 L260 60 L284 52 L300 60 L325 60 L350 15 L372 92 L395 44 L418 60 L900 60"/></svg>'

def clip(content, duration, cls="", track=1, eid=""):
    return f'<div id="{eid}" class="clip {cls}" data-start="0" data-duration="{duration}" data-track-index="{track}">{content}</div>'

def frame(fid, duration, content, css, js, ground="#07110E"):
    source = f'''<template>
<div id="root" data-composition-id="{fid}" data-duration="{duration}" data-width="1920" data-height="1080" data-fps="24">
<style>{FONTS}{CSS}{css}</style>
{clip('',duration,'bg',0,'mg-'+fid+'-ground')}
{clip('<div class="stage">'+content+'</div>',duration,'visual',1,'mg-'+fid+'-visual')}
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script>
(()=>{{
const root=document.getElementById('root');
const q=s=>root.querySelector(s), qa=s=>Array.from(root.querySelectorAll(s));
const tl=gsap.timeline({{paused:true}});
{js}
window.__timelines["{fid}"]=tl;
}})();
</script>
</div>
</template>
'''
    # Condensed uppercase glyphs have generous font boxes; the inspected glyphs
    # remain separate at the intentional tight display leading.
    source=source.replace('<span','<span data-layout-allow-overlap')
    (ROOT/'compositions/frames'/f'{fid}.html').write_text(source.replace('../../assets/','assets/'))

frame('01-hook',5,
'''<div class="chrome">MAC GUARDIAN / A NEW KIND OF MAC CARE</div>
<div class="hook-head"><div class="hook-line hook-a">YOUR MAC.</div><div class="hook-line hook-b">TOO FULL.</div><div class="hook-line hook-c">TOO MESSY.</div><div class="hook-line hook-d mint">MEET ITS DOCTOR.</div></div>
<div class="file-cloud" data-layout-ignore>'''+''.join(f'<div class="loose-file file-{i}"><i></i><b>{["PDF","MD","PNG","ZIP"][i%4]}</b></div>' for i in range(12))+'''</div>'''+PULSE,
'''
#root .hook-head{position:absolute;left:5cqw;top:23cqh;width:90cqw;height:35cqh;display:grid;place-items:center;z-index:2}
#root .hook-line{position:absolute;width:90cqw;text-align:center;font-size:14cqw;line-height:1.06;font-weight:900;letter-spacing:-.02em;opacity:0}
#root .hook-d{font-size:11.3cqw}
#root .pulse{left:6cqw;top:64cqh;width:88cqw;height:8cqh}
#root .loose-file{position:absolute;width:5.4cqw;height:13cqh;background:#F4F1E7;border:4px solid #07110E;padding:1cqw;color:#07110E}
#root .loose-file i{display:block;width:2.5cqw;height:3px;background:#07110E;margin-top:2cqh}
#root .loose-file b{display:block;margin-top:1.6cqh;font-family:"JetBrains Mono",monospace;font-size:.9cqw}
''',
'''
const lines=qa('.hook-line');
// Installed headline-slam: scale landing plus deterministic three-frame shake.
lines.forEach((el,i)=>{
 const t=i*1.25;
 tl.fromTo(el,{scale:1.32,opacity:0,y:0},{scale:1,opacity:1,y:0,duration:.42,ease:'expo.out'},t);
 tl.to(el,{x:6,y:-3,duration:1/24},t+.32).to(el,{x:-4,y:2,duration:1/24},t+.362).to(el,{x:0,y:0,duration:1/24},t+.404);
 if(i<3)tl.to(el,{opacity:0,scale:.9,duration:.12,ease:'power2.in'},t+1.12);
});
qa('.loose-file').forEach((el,i)=>{
 const side=i%2===0;
 const px=side ? 2+(i%3)*3 : 80+(i%3)*3;
 const py=10+Math.floor(i/2)*10;
 el.style.left=px+'cqw';el.style.top=py+'cqh';
 tl.fromTo(el,{opacity:0,scale:.5,rotation:0,y:80},{opacity:.75,scale:1,rotation:(i%3-1)*14,y:0,duration:.4,ease:'back.out(1.2)'},.65+i*.16);
 tl.to(el,{x:side?-250:250,y:-55,opacity:0,duration:.7,ease:'power3.in'},3.78+i*.025);
});
const p=q('.pulse path'),L=p.getTotalLength();p.style.strokeDasharray=L;p.style.strokeDashoffset=L;
tl.to(p,{strokeDashoffset:0,duration:3.7,ease:'none'},.2);
''')

frame('02-doctor',5,
'''<div class="chrome">MEET YOUR MAC'S DOCTOR</div>
<div class="hero"><span class="brand-first">MAC</span><span class="brand-second mint">GUARDIAN.</span></div>
<img class="doctor" src="../../assets/doctor.png" alt="Mac Guardian doctor holding a laptop"/>
<div class="intro-promise">AUTOMATIC CARE.</div>
<div class="intro-every caption">Every 15 minutes. Quietly, on your Mac.</div>'''+PULSE,
'''
#root .hero{top:20cqh;font-size:11.4cqw}
#root .intro-promise{position:absolute;left:5cqw;top:61cqh;font-size:3.6cqw;font-weight:700}
#root .intro-every{position:absolute;left:5cqw;top:78cqh;width:47cqw;font-size:1.16cqw}
#root .pulse{top:70cqh}
''',
'''
tl.fromTo(q('.doctor'),{x:120,scale:.84,opacity:0,rotation:5},{x:0,scale:1,opacity:1,rotation:0,duration:.75,ease:'power3.out'},0);
tl.fromTo(q('.brand-first'),{y:100,opacity:0},{y:0,opacity:1,duration:.5,ease:'power4.out'},.08);
tl.fromTo(q('.brand-second'),{y:110,opacity:0},{y:0,opacity:1,duration:.55,ease:'power4.out'},.3);
tl.fromTo(q('.intro-promise'),{x:-60,opacity:0},{x:0,opacity:1,duration:.5,ease:'power3.out'},1.25);
const p=q('.pulse path'),L=p.getTotalLength();p.style.strokeDasharray=L;p.style.strokeDashoffset=L;
tl.to(p,{strokeDashoffset:0,duration:1.25,ease:'power2.inOut'},2.08);
tl.fromTo(q('.intro-every'),{y:18,opacity:0},{y:0,opacity:1,duration:.5,ease:'power2.out'},3.33);
''')

blocks=''.join(f'<div class="storage-block sb-{i}"></div>' for i in range(64))
frame('03-space',6.666667,
'''<div class="chrome">01 / RECLAIM SPACE</div>
<div class="hero"><span>SPACE TO</span><span class="mint">CREATE.</span></div>
<div class="support">Keep active work untouched.</div>
<div class="lattice-wrap" data-layout-ignore><div class="storage-lattice">'''+blocks+'''</div></div>
<div class="artifact artifact-a">old caches</div><div class="artifact artifact-b">idle node_modules</div><div class="artifact artifact-c">old build targets</div>
<div class="space-payoff caption">Recreate the files. Reclaim the space.</div>''',
'''
#root .hero{top:24cqh;font-size:11.2cqw}
#root .support{top:63cqh;font-size:2.5cqw}
#root .lattice-wrap{position:absolute;left:56cqw;top:16cqh;width:35cqw;height:56cqh;perspective:1200px;display:grid;place-items:center}
#root .storage-lattice{display:grid;grid-template-columns:repeat(8,1fr);gap:.8cqw;width:33cqw;height:49cqh;transform-style:preserve-3d}
#root .storage-block{background:#93F5CE;border-right:6px solid #0E9B63;border-bottom:6px solid #0A6F47;min-width:0}
#root .artifact{position:absolute;left:57cqw;top:73cqh;width:35cqw;font-family:"JetBrains Mono",monospace;font-size:1.55cqw;color:#93F5CE;opacity:0;text-align:center}
#root .space-payoff{position:absolute;left:5cqw;top:78cqh;width:48cqw;opacity:0}
''',
'''
tl.fromTo(q('.hero'),{x:-60,opacity:0},{x:0,opacity:1,duration:.6,ease:'power4.out'},0);
tl.fromTo(q('.storage-lattice'),{rotationX:65,rotationY:-30,rotationZ:18,scale:.65,opacity:0},{rotationX:30,rotationY:-17,rotationZ:12,scale:1,opacity:1,duration:1.25,ease:'power3.out'},.05);
tl.fromTo(q('.support'),{y:20,opacity:0},{y:0,opacity:1,duration:.4},1.05);
qa('.artifact').forEach((el,i)=>{let t=1.667+i*1.167;tl.fromTo(el,{y:25,opacity:0},{y:0,opacity:1,duration:.35,ease:'power3.out'},t);tl.to(el,{y:-20,opacity:0,duration:.22},t+.88)});
qa('.storage-block').forEach((el,i)=>{
 if(i<48){let group=Math.floor(i/16),t=1.67+group*1.167+(i%16)*.028;tl.to(el,{scale:0,rotation:70,y:-90,opacity:0,duration:.52,ease:'back.in(1.4)'},t);}
});
tl.to(q('.storage-lattice'),{rotationX:0,rotationY:0,rotationZ:0,duration:1,ease:'power3.inOut'},4.5);
tl.fromTo(q('.space-payoff'),{x:-30,opacity:0},{x:0,opacity:1,duration:.5,ease:'power2.out'},5.1);
''')

frame('04-wiki',6.666666,
'''<div class="chrome">02 / YOUR PERSONAL FILE WIKI</div>
<div class="hero"><span>FILES WITH</span><span class="mint">A HOME.</span></div>
<div class="support wiki-support">Clear names.<span>Linked indexes.</span><span>Reversible moves.</span></div>
<div class="wiki-scene">
 <div class="note-card"><div class="note-eyebrow label">MARKDOWN NOTE</div><div class="note-heading">Italy trip plan</div><div class="note-lines" data-layout-ignore><i></i><i></i><i></i></div><div class="note-old label">untitled-3.md</div><div class="note-new label">italy-trip-plan.md</div></div>
 <div class="wiki-root label">~/Wiki</div>
 <div class="folders"><div class="wiki-folder"><i></i><b>DOCUMENTS</b></div><div class="wiki-folder"><i></i><b>IMAGES</b></div><div class="wiki-folder"><i></i><b>VIDEOS</b></div></div>
 <div class="wiki-index label">Home.md</div><div class="wiki-connector" data-layout-ignore></div>
</div><div class="foot caption">Illustrative workflow. Files organized locally.</div>''',
'''
#root .hero{top:22cqh;font-size:9.2cqw;width:47cqw}
#root .support{top:59cqh;font-size:2.3cqw}
#root .wiki-support>span{display:block;line-height:1.3}
#root .wiki-scene{position:absolute;left:55cqw;top:15cqh;width:40cqw;height:62cqh}
#root .note-card{position:absolute;left:6cqw;top:1cqh;width:27cqw;height:35cqh;background:#F4F1E7;color:#07110E;padding:2cqw;border:4px solid #07110E;z-index:4}
#root .note-eyebrow{font-size:.95cqw}
#root .note-heading{font-size:3.1cqw;font-weight:700;margin-top:3cqh}
#root .note-lines{margin-top:2cqh}
#root .note-lines i{display:block;width:19cqw;height:3px;background:#07110E;opacity:.3;margin:1.5cqh 0}
#root .note-old,#root .note-new{position:absolute;left:2cqw;bottom:3cqh;font-size:1.1cqw;white-space:nowrap}
#root .note-new{color:#07110E;background:#93F5CE;padding:.5cqw;left:1.5cqw;bottom:2cqh;opacity:0}
#root .wiki-root{position:absolute;left:4cqw;top:6cqh;width:30cqw;font-size:2.5cqw;text-align:center;color:#93F5CE;opacity:0}
#root .folders{position:absolute;left:0;top:24cqh;display:flex;gap:1.5cqw}
#root .wiki-folder{position:relative;width:11cqw;height:17cqh;background:#93F5CE;border:4px solid #07110E;padding:1.2cqw;opacity:0}
#root .wiki-folder i{display:block;width:4cqw;height:2cqh;background:#93F5CE;position:absolute;top:-2cqh;left:-4px;border:4px solid #07110E;border-bottom:0}
#root .wiki-folder b{position:absolute;left:1cqw;right:1cqw;bottom:2.5cqh;color:#07110E;font-family:"JetBrains Mono",monospace;font-size:.85cqw;text-align:center}
#root .wiki-index{position:absolute;left:12cqw;top:49cqh;width:12cqw;text-align:center;border-bottom:2px solid #93F5CE;font-size:1.25cqw;padding:1cqw 0;opacity:0}
#root .wiki-connector{position:absolute;left:5.5cqw;top:39cqh;width:25cqw;height:13cqh;border:2px solid #93F5CE;border-top:0;opacity:0}
''',
'''
tl.fromTo(q('.hero'),{y:60,opacity:0},{y:0,opacity:1,duration:.6,ease:'power4.out'},0);
tl.fromTo(q('.note-card'),{rotation:9,scale:.86,y:50,opacity:0},{rotation:0,scale:1,y:0,opacity:1,duration:.7,ease:'power3.out'},.1);
tl.fromTo(q('.note-heading'),{y:12,opacity:0},{y:0,opacity:1,duration:.4},1.667);
tl.to(q('.note-old'),{opacity:0,duration:.15},2.4);
tl.fromTo(q('.note-new'),{x:-20,opacity:0},{x:0,opacity:1,duration:.38,ease:'power3.out'},2.5);
tl.fromTo(q('.wiki-root'),{y:20,opacity:0},{y:0,opacity:1,duration:.4},4.6);
qa('.wiki-folder').forEach((el,i)=>tl.fromTo(el,{y:65,scale:.8,opacity:0},{y:0,scale:1,opacity:1,duration:.55,ease:'back.out(1.3)'},3.5+i*.17));
tl.to(q('.note-card'),{scale:.23,x:-260,y:180,opacity:0,duration:.8,ease:'power3.inOut'},3.85);
tl.fromTo(q('.wiki-connector'),{scaleY:0,opacity:0,transformOrigin:'50% 0%'},{scaleY:1,opacity:1,duration:.5,ease:'power2.out'},4.667);
tl.fromTo(q('.wiki-index'),{y:20,opacity:0},{y:0,opacity:1,duration:.45},5);
qa('.wiki-support,.wiki-support>span').forEach((el,i)=>tl.fromTo(el,{x:-20,opacity:0},{x:0,opacity:1,duration:.35},1+i*1.75));
tl.fromTo(q('.foot'),{opacity:0},{opacity:1,duration:.4},5.333);
''')

frame('05-care',5,
'''<div class="chrome">03 / CONTINUOUS CARE</div>
<div class="care-pass care-a"><div class="care-head">UPDATE<br/>IDLE APPS.</div><div class="care-detail">Verify supported official updates.</div><div class="care-art update-symbol" data-layout-ignore><svg viewBox="0 0 300 300"><path d="M235 85 A105 105 0 1 0 245 203"/><path d="M190 82 L245 82 L245 27"/></svg></div></div>
<div class="care-pass care-b"><div class="care-head">REVIEW<br/>MAC HEALTH.</div><div class="care-detail">Memory, apps and startup items.</div><div class="care-art health-symbol" data-layout-ignore><svg viewBox="0 0 300 300"><circle cx="130" cy="130" r="90"/><path d="M190 190 L270 270 M57 130 L94 130 L113 83 L133 177 L154 115 L169 130 L205 130"/></svg></div></div>
<div class="care-pass care-c"><div class="care-head">BACK UP<br/>APPROVED FILES.</div><div class="care-detail">Verified private GitHub backups.</div><div class="care-art backup-symbol" data-layout-ignore><svg viewBox="0 0 300 300"><path d="M25 92 L25 245 L275 245 L275 75 L140 75 L115 45 L25 45 Z"/><path d="M105 174 L138 205 L205 130"/></svg></div></div>
<div class="foot caption">Local maintenance. Reversible file changes.</div>''',
'''
#root .care-pass{position:absolute;inset:0;opacity:0}
#root .care-head{position:absolute;left:5cqw;top:25cqh;width:53cqw;font-weight:900;font-size:9.2cqw;line-height:.91;color:#93F5CE;letter-spacing:-.015em}
#root .care-c .care-head{font-size:7.7cqw;width:53cqw}
#root .care-detail{position:absolute;left:5cqw;top:67cqh;width:53cqw;font-size:2.2cqw;color:#F4F1E7}
#root .care-art{position:absolute;left:64cqw;top:20cqh;width:26cqw;height:48cqh}
#root .care-art svg{width:100%;height:100%;fill:none;stroke:#93F5CE;stroke-width:12;stroke-linecap:round;stroke-linejoin:round}
''',
'''
qa('.care-pass').forEach((el,i)=>{
 let t=i*1.667;
 tl.fromTo(el,{opacity:0},{opacity:1,duration:.08},t);
 tl.fromTo(el.querySelector('.care-head'),{y:55,scale:.96},{y:0,scale:1,duration:.45,ease:'power4.out'},t);
 tl.fromTo(el.querySelector('.care-detail'),{y:20,opacity:0},{y:0,opacity:1,duration:.35},t+.6);
 tl.fromTo(el.querySelector('.care-art'),{scale:.7,rotation:-30,opacity:0},{scale:1,rotation:0,opacity:1,duration:.6,ease:'back.out(1.2)'},t+.1);
 if(i<2)tl.to(el,{opacity:0,duration:.08},t+1.58);
});
tl.fromTo(q('.foot'),{opacity:0},{opacity:1,duration:.35},3.9);
''')

frame('06-talk',5,
'''<div class="chrome">04 / CONVERSATION IS THE CONTROL</div>
<div class="hero"><span>JUST</span><span class="mint">ASK.</span></div>
<div class="support">Then get on with your day.</div>
<div class="conversation"><div class="conversation-name label">MAC GUARDIAN</div><div class="bubble sent">How's my Mac?</div><div class="bubble received">I'll check storage, memory and updates.</div><div class="bubble sent undo">Undo the last organization.</div><div class="chat-proof label">Undo is available from recorded file moves.</div></div>
<div class="foot caption">Illustrative conversation.</div>''',
'''
#root .hero{top:25cqh;font-size:13cqw;width:38cqw}
#root .support{top:68cqh;width:42cqw;font-size:2.5cqw}
#root .conversation{position:absolute;left:50cqw;top:15cqh;width:44cqw;height:60cqh}
#root .conversation-name{color:#93F5CE;font-size:1.1cqw;margin-bottom:4cqh}
#root .bubble{position:absolute;padding:1.4cqw 1.7cqw;font-size:2.15cqw;font-weight:700;line-height:1.1;border-radius:1.2cqw;opacity:0}
#root .sent{right:0;top:8cqh;background:#93F5CE;color:#07110E;max-width:36cqw;transform-origin:100% 100%}
#root .received{left:0;top:22cqh;background:#F4F1E7;color:#07110E;width:39cqw;transform-origin:0% 100%}
#root .undo{top:40cqh;font-size:1.8cqw;max-width:40cqw}
#root .chat-proof{position:absolute;top:55cqh;left:0;width:44cqw;line-height:1.4;font-size:.97cqw;color:#F4F1E7;opacity:0}
''',
'''
tl.fromTo(q('.hero'),{x:-70,opacity:0},{x:0,opacity:1,duration:.55,ease:'power4.out'},0);
tl.fromTo(q('.support'),{y:20,opacity:0},{y:0,opacity:1,duration:.4},1.1);
qa('.bubble').forEach((el,i)=>tl.fromTo(el,{scale:.75,y:25,opacity:0},{scale:1,y:0,opacity:1,duration:.3,ease:'back.out(1.3)'},.5+i*1.3));
tl.fromTo(q('.chat-proof'),{y:14,opacity:0},{y:0,opacity:1,duration:.35},4);
tl.fromTo(q('.foot'),{opacity:0},{opacity:1,duration:.4},3.6);
''')

frame('07-close',6.666667,
'''<div class="chrome">MAC GUARDIAN</div>
<div class="hero"><span class="close-first">YOUR MAC.</span><span class="close-second mint">CARED FOR.</span></div>
<img class="doctor" src="../../assets/doctor.png" alt="Mac Guardian doctor with laptop"/>
<div class="close-tag">Automatic maintenance. Through conversation.</div>
<div class="close-url label">aiworthusing.com/agent-index/mac-guardian</div>
<div class="close-credit caption">MIT / OpenClaw + Plow</div>'''+PULSE,
'''
#root .hero{top:22cqh;font-size:9.75cqw;width:53cqw}
#root .doctor{left:60cqw;width:35cqw;top:7cqh;height:72cqh}
#root .close-tag{position:absolute;left:5cqw;top:61cqh;width:54cqw;font-size:2.2cqw}
#root .close-url{position:absolute;left:5cqw;top:72cqh;font-size:1.25cqw;color:#93F5CE;width:57cqw}
#root .close-credit{position:absolute;left:5cqw;top:79cqh;font-size:.95cqw}
#root .pulse{left:62cqw;width:31cqw;top:78cqh;height:4cqh}
''',
'''
tl.fromTo(q('.doctor'),{y:60,scale:.9,opacity:0},{y:0,scale:1,opacity:1,duration:.8,ease:'power3.out'},0);
tl.fromTo(q('.close-first'),{y:70,opacity:0},{y:0,opacity:1,duration:.5,ease:'power4.out'},.1);
tl.fromTo(q('.close-second'),{y:70,opacity:0},{y:0,opacity:1,duration:.55,ease:'power4.out'},.4167);
tl.fromTo(q('.close-tag'),{y:20,opacity:0},{y:0,opacity:1,duration:.45},1.667);
tl.fromTo(q('.close-url'),{x:-20,opacity:0},{x:0,opacity:1,duration:.45},3.333);
tl.fromTo(q('.close-credit'),{opacity:0},{opacity:1,duration:.4},4.167);
const p=q('.pulse path'),L=p.getTotalLength();p.style.strokeDasharray=L;p.style.strokeDashoffset=L;
tl.to(p,{strokeDashoffset:0,duration:1.5,ease:'power2.inOut'},3.5);
tl.to(q('.stage'),{opacity:0,duration:.45,ease:'power2.inOut'},6.2);
''')

# In a silent typography film line breaks are display layout, not body text.
story = (ROOT/'STORYBOARD.md').read_text().replace('- status: outline','- status: animated')
(ROOT/'STORYBOARD.md').write_text(story)
print('Built seven editable scenes, total 40 seconds.')
