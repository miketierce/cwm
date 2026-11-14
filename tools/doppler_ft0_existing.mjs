#!/usr/bin/env node
/**
 * CWM Doppler-inspired frequency-warp FT-0 (retrospective).
 * Run from repository root: node tools/doppler_ft0_existing.mjs
 * No hardware or external packages required.
 * Outputs: data/results/doppler/doppler_ft0_20261114.json
 *
 * This replays historical complex H(f), NOT a moving physical source,
 * NOT simultaneous measured three-tone queries, NOT computing advantage.
 */
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
const analyze = function analyze(sessions) {
  const f0s=[31000,32000,33000,34000,35000,36000,37000,38000];
  const shifts=[-1000,-500,0,500,1000],paths=["F1","F2"],conditions=["GLASS","LOOPBACK","ELECTRICAL_ONLY"];
  const z=x=>[x.H_mean_re,x.H_mean_im];
  const plus=(a,b)=>[a[0]+b[0],a[1]+b[1]];
  const minus=(a,b)=>[a[0]-b[0],a[1]-b[1]];
  const times=(a,b)=>[a[0]*b[0]-a[1]*b[1],a[0]*b[1]+a[1]*b[0]];
  const scale=(a,s)=>[a[0]*s,a[1]*s];
  const conj=x=>[x[0],-x[1]],squared=x=>x[0]*x[0]+x[1]*x[1];
  const median=x=>{let a=[...x].sort((a,b)=>a-b);return (a[(a.length-1)>>1]+a[a.length>>1])/2;};
  const get=(si,c,p,f)=>sessions[si].states[`${c}:${p}`].per_freq[String(f)];
  const m=(c,p,f)=>scale(plus(z(get(0,c,p,f)),z(get(1,c,p,f))),.5);
  const vec=(si,c,p,f0,shift,n=3)=>Array.from({length:n},(_,i)=>z(get(si,c,p,(i+1)*(f0+shift))));
  const tvec=(c,p,f0,shift,n=3)=>Array.from({length:n},(_,i)=>m(c,p,(i+1)*(f0+shift)));
  function residual(y,t,kind="complex"){
    let den=0,err=0;
    if(kind==="complex"){
      let a=[0,0],dt=0;
      for(let i=0;i<y.length;i++){a=plus(a,times(conj(t[i]),y[i]));dt+=squared(t[i]);den+=squared(y[i]);}
      a=scale(a,1/(dt+1e-24));
      for(let i=0;i<y.length;i++)err+=squared(minus(y[i],times(a,t[i])));
    }else{
      const yy=y.map(x=>Math.sqrt(squared(x))),tt=t.map(x=>Math.sqrt(squared(x)));
      const a=yy.reduce((v,x,i)=>v+x*tt[i],0)/(tt.reduce((v,x)=>v+x*x,0)+1e-24);
      for(let i=0;i<yy.length;i++){err+=(yy[i]-a*tt[i])**2;den+=yy[i]**2;}
    }
    return err/(den+1e-24);
  }
  const statuses=[];
  for(const c of conditions)for(const n of [2,3])for(const kind of ["complex","magnitude"]){
    const acc={condition:c,harmonics:n,method:kind,n_cases:0,known_path_shift_hit:0,blind_path_hit:0,joint_path_hit:0,joint_shift_hit:0,joint_both_hit:0,blind_path_by_shift:{}};
    for(const p of paths)for(const f0 of f0s)for(const d of shifts){
      const y=vec(2,c,p,f0,d,n);
      const known=shifts.map(dd=>({d:dd,error:residual(y,tvec(c,p,f0,dd,n),kind)})).sort((a,b)=>a.error-b.error||a.d-b.d)[0];
      const blind=paths.map(pp=>({p:pp,error:residual(y,tvec(c,pp,f0,0,n),kind)})).sort((a,b)=>a.error-b.error||a.p.localeCompare(b.p))[0];
      const joint=paths.flatMap(pp=>shifts.map(dd=>({p:pp,d:dd,error:residual(y,tvec(c,pp,f0,dd,n),kind)}))).sort((a,b)=>a.error-b.error||a.p.localeCompare(b.p)||a.d-b.d)[0];
      acc.n_cases++;
      acc.known_path_shift_hit+=Number(known.d===d);
      acc.blind_path_hit+=Number(blind.p===p);
      acc.joint_path_hit+=Number(joint.p===p);
      acc.joint_shift_hit+=Number(joint.d===d);
      acc.joint_both_hit+=Number(joint.p===p&&joint.d===d);
      if(!acc.blind_path_by_shift[d])acc.blind_path_by_shift[d]={total:0,hits:0};
      acc.blind_path_by_shift[d].total++;
      acc.blind_path_by_shift[d].hits+=Number(blind.p===p);
    }
    statuses.push(acc);
  }
  const shape=[];
  for(const c of conditions){
    let drift=[],shift500=[],shift1000=[];
    for(const p of paths)for(const f0 of f0s){
      const base=vec(2,c,p,f0,0);
      drift.push(Math.sqrt(residual(base,vec(0,c,p,f0,0))));
      shift500.push(Math.sqrt(residual(vec(2,c,p,f0,500),base)));
      shift1000.push(Math.sqrt(residual(vec(2,c,p,f0,1000),base)));
    }
    shape.push({condition:c,independent_base_path_pairs:16,median_session_S1_to_S3_shape_delta:median(drift),median_plus500Hz_shape_delta:median(shift500),median_plus1000Hz_shape_delta:median(shift1000),ratio_plus500_to_crosssession:median(shift500)/median(drift)});
  }
  let seed=3429671;
  function rng(){seed=(seed+0x6d2b79f5)|0;let t=seed;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return ((t^(t>>>14))>>>0)/4294967296;}
  function normal(){return Math.sqrt(-2*Math.log(Math.max(rng(),1e-12)))*Math.cos(2*Math.PI*rng());}
  function perturb(x,amp,phase){const a=1+amp*normal(),b=phase*normal();return times(x,[a*Math.cos(b),a*Math.sin(b)]);}
  const monteCarlo=[];
  for(const c of conditions){
    const cases=[];
    for(const p of paths)for(const f0 of f0s)for(const d of shifts){
      const fs=[1,2,3].map(n=>n*(f0+d));
      const raw=fs.map(f=>z(get(2,c,p,f)));
      const sigmas=fs.map(f=>{const v=get(2,c,p,f);return {amp:v.H_abs_cv,phase:v.H_phase_circ_std_deg*Math.PI/180};});
      const templates=paths.flatMap(pp=>shifts.map(dd=>({p:pp,d:dd,vec:tvec(c,pp,f0,dd)})));
      cases.push({p,f0,d,raw,sigmas,templates});
    }
    for(const sig of [0,.0025,.005,.01,.02,.05]){
      let pathHit=0,shiftHit=0,bothHit=0,total=0;
      for(const sample of cases)for(let k=0;k<50;k++){
        const y=sample.raw.map((x,i)=>perturb(x,sig===0?Math.min(sample.sigmas[i].amp,1):sig,sig===0?Math.min(sample.sigmas[i].phase,1):sig));
        let best={error:Infinity};
        for(const candidate of sample.templates){
          const e=residual(y,candidate.vec);
          if(e<best.error)best={p:candidate.p,d:candidate.d,error:e};
        }
        pathHit+=Number(best.p===sample.p);
        shiftHit+=Number(best.d===sample.d);
        bothHit+=Number(best.p===sample.p&&best.d===sample.d);
        total++;
      }
      monteCarlo.push({condition:c,noise:sig===0?"model_from_recorded_CV_and_phase_std":sig,total_synthetic_jitters:total,path_accuracy:pathHit/total,shift_accuracy:shiftHit/total,joint_accuracy:bothHit/total});
    }
  }
  const noiseMedians=[];
  for(const c of conditions)for(const p of paths){
    const rows=Object.values(sessions[2].states[c+":"+p].per_freq);
    noiseMedians.push({condition:c,path:p,median_H_magnitude_CV:median(rows.map(x=>x.H_abs_cv)),median_H_phase_std_deg:median(rows.map(x=>x.H_phase_circ_std_deg)),median_RX_SNR_ratio:median(rows.map(x=>x.rx_snr_median))});
  }
  return {
    model_id:"CWM-DOP-FT0-RETROSPECTIVE-20261114",
    maturity:"EXPLORATORY MODEL / NOT HARDWARE DOPPLER / NOT PREREGISTERED",
    input:"3 historical 181-point (500Hz step) FT1 transfer summaries for GLASS, ELECTRICAL_ONLY, LOOPBACK and two TX paths",
    split:{train:["FT1-S1","FT1-S2"],test:"FT1-S3"},
    synthetic_query:{fundamentals_hz:f0s,shift_of_fundamental_hz:shifts,harmonics:[1,2,3],response:"H(f)*unit-amplitude line at each of the three frequencies, summed only conceptually; no fresh simultaneous-tritone capture",n_scenarios_per_condition:80,frequency_warp:"f0 + delta, 2*(f0 + delta), 3*(f0 + delta)",nco_caveat:"Recorded FT1 NCO actual harmonic frequencies may differ from commanded grid by 15-52Hz; model does not correct this"},
    estimator:"least-squares complex scalar fit per candidate (absorbs common gain and phase), normalized L2 residual across harmonics; templates are arithmetic means of S1/S2 H; optional magnitude-only comparator",
    model_accuracy:statuses,
    relative_shape_sensitivity:shape,
    measurement_variability:noiseMedians,
    monte_carlo:{seed:3429671,jitters_per_synthetic_case:50,noise_assumption:"independent multiplicative Gaussian amplitude noise and Gaussian phase jitter per harmonic, with either measured S3 per-frequency CV/phase_std or common stress level; not observed hardware data",results:monteCarlo},
    caveats:[
      "Classification targets an idealized known family of shifted harmonic input frequencies. This is not actual Doppler from a moving source.",
      "80 scenarios reuse the same measured transfer-map points; they are not 80 independent physical captures and no binomial CI is valid.",
      "Model generated using single-frequency grid measurements; simultaneous multitone behavior and continuous acceleration have not been captured.",
      "Source frequency/shift is commanded in this replay. This is an observability check, not evidence of source-blind Doppler sensing or compute advantage.",
      "NCO frequency mismatches and 500Hz grid limit precision, especially for shifts much smaller than 500Hz.",
      "F1 and F2 are distinct drive paths on a shared physical plate, not task-trained competing resonator devices.",
      "Loopback shares high deterministic shift accuracy, so high accuracy alone is not a glass-specific computation result.",
      "The model uses a digital template search and ADC-derived H, not a physical low-output compatibility score.",
      "Per-trial raw waveform validation and measured whole-system power/latency/ADC/resource cost are not part of this retrospective model.",
      "E24's 4/4 frequency-offset run is not a valid Doppler robustness check because its scorer applies enrollment peak labels to the unshifted frequencies; this model does not reuse its claimed accuracy.",
      "FT1 originally ended INCONCLUSIVE under preregistered rules, not reversed by this post hoc model."
    ],
    decision:{physics_replay:"PROMISING: physical response shape is much more shift-sensitive than the glass cross-session shape drift at the tested 500-1000Hz offsets",invariant_recognition:"NOT SHOWN: blind path identity drops on shifted queries; shift-aware digital template search restores it",glass_specific_compute:"NOT SHOWN: loopback also predicts shift/path accurately and no analog score cost advantage was measured",next_step:"Fresh shifted physical multitone queries, unknown shift to the scorer, electrical/loopback/source-only controls, and independent later sessions; target <500Hz shifts using finer capture grid"}
  };
};
const root = process.cwd();
const inputIds = ['FT1-S1','FT1-S2','FT1-S3'];
const sessions = inputIds.map(id => JSON.parse(readFileSync(resolve(root, 'data/results/k_eff', id, 'derived/summary.json'),'utf8')));
const result = analyze(sessions);
result.sources = inputIds.map(id=>({path:'data/results/k_eff/'+id+'/derived/summary.json'}));
const dest = resolve(root,process.argv[2] || 'data/results/doppler/doppler_ft0_20261114.json');
mkdirSync(dirname(dest),{recursive:true});
writeFileSync(dest,JSON.stringify(result,null,2)+'\n');
for(const c of ['GLASS','LOOPBACK','ELECTRICAL_ONLY']){
 const x=result.model_accuracy.find(x=>x.condition===c&&x.harmonics===3&&x.method==='complex');
 const s=result.relative_shape_sensitivity.find(x=>x.condition===c);
 console.log(c+': shift-known-path '+x.known_path_shift_hit+'/'+x.n_cases+
   '; blind path '+x.blind_path_hit+'/'+x.n_cases+
   '; joint shift-aware '+x.joint_both_hit+'/'+x.n_cases+
   '; median shape delta @+500Hz '+s.median_plus500Hz_shape_delta.toFixed(4));
}
console.log('Wrote '+dest);
