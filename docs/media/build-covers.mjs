// SPDX-License-Identifier: Apache-2.0
// Original EgoLabs visual source. Generated artwork: CC BY 4.0.
// node docs/media/build-covers.mjs ego [--png]
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import path from 'node:path';

const project = process.argv[2] || 'ego';
if (!['ego', 'egolink'].includes(project)) throw new Error('Choose ego or egolink');
const output = path.dirname(fileURLToPath(import.meta.url));
const palette = { bg:'#080a08', panel:'#111410', text:'#f0f3ea', muted:'#a1ab9a', line:'#30362c', lime:'#b4ff5a' };
const esc = s => s.replaceAll('&','&amp;').replaceAll('<','&lt;');
const text = (x,y,value,size,fill=palette.text,extra='') => `<text x="${x}" y="${y}" font-size="${size}" fill="${fill}" ${extra}>${esc(value)}</text>`;
const mark = (x,y,size,color) => `<path d="M${x},${y}h${size}v${size*.65}h-${size*.35}v${size*.35}H${x}Z" fill="${color}"/>`;

function cover(social=false) {
  const w=1600, h=social?840:640;
  const cy=social?390:307;
  const title=project==='ego'?'Ego — Your AI. Your data. Your rules.':'EgoLink — A physical connection to personal AI.';
  const name=project==='ego'?'PROJECT EGO':'EGOLINK / ENGINEERING PROTOTYPE';
  let s=`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-labelledby="title desc"><title id="title">${esc(title)}</title><desc id="desc">EgoLabs open development. Abstract brand artwork, not a product photograph or hardware drawing.</desc><rect width="${w}" height="${h}" fill="${palette.bg}"/><g font-family="Arial, Helvetica, sans-serif">`;
  s+=mark(78,52,27,palette.lime)+text(120,76,'EgoLabs',29,palette.text,'font-weight="700" letter-spacing="-1"');
  s+=text(1520,74,'OPEN DEVELOPMENT',17,palette.muted,'text-anchor="end" letter-spacing="2.4"');
  s+=text(80,social?160:139,name,18,palette.lime,'letter-spacing="2.1" font-weight="700"');
  if(project==='ego') {
    const y=social?285:244, step=social?108:99;
    ['Your AI.','Your data.','Your rules.'].forEach((line,i)=>s+=text(74,y+i*step,line,social?110:100,i===2?palette.lime:palette.text,'font-weight="700" letter-spacing="-5"'));
  } else {
    s+=text(74,social?302:273,'EgoLink',social?132:122,palette.text,'font-weight="700" letter-spacing="-6"');
    s+=text(80,social?390:350,'A physical connection',47,palette.text,'letter-spacing="-1.3"');
    s+=text(80,social?449:409,'to personal AI.',47,palette.text,'letter-spacing="-1.3"');
    s+=text(82,social?512:464,'Hardware · firmware · services',22,palette.muted);
  }
  // An abstract, cut-corner mark extends the existing website identity.
  // It deliberately carries no invented hardware geometry or capability claim.
  const gx=1120, gy=cy;
  s+=`<g transform="translate(${gx} ${gy})">`;
  [420,330,240].forEach((size,i)=>{
    const half=size/2;
    s+=`<path d="M${-half},${-half}H${half}V${half*.30}H${half*.30}V${half}H${-half}Z" fill="none" stroke="${i===2?'#657950':palette.line}" stroke-width="${i===2?2:1.5}"/>`;
  });
  s+=mark(-77,-77,154,palette.lime);
  s+='</g>';
  const rule=h-114;
  s+=`<path d="M80 ${rule}H1520" stroke="${palette.line}" stroke-width="1"/>`;
  s+=text(80,h-64,project==='ego'?'PERSONAL AI, BUILT IN THE OPEN.':'BUILDING THE WEARABLE, IN THE OPEN.',22,palette.text,'font-weight="700" letter-spacing=".8"');
  s+=text(80,h-30,project==='ego'?'EgoLink + EgoBase · code, experiments and decisions':'Real prototypes · visible experiments · continuous development',19,palette.muted);
  s+=text(1520,h-58,'getego.ai',27,palette.lime,'text-anchor="end"');
  s+='</g></svg>\n';
  return s;
}

await mkdir(output,{recursive:true});
for(const [suffix,social] of [['cover',false],['social',true]]) {
  const svg=cover(social);
  await writeFile(path.join(output,`${project}-${suffix}.svg`),svg);
  if(process.argv.includes('--png')) {
    const sharp=createRequire(import.meta.url)('sharp');
    await sharp(Buffer.from(svg)).resize(social?1200:1600,social?630:640).png().toFile(path.join(output,`${project}-${suffix}.png`));
  }
}
console.log(`Generated ${project} cover and sharing artwork.`);
