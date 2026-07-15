// Extrai do v7 (headless) as paredes da 109.1506 e a referência de peças/kg
// por parede. O asset é READ-ONLY: este script só o lê.
// Uso: node tools/extrair_estrutura_v7.mjs > tests/fixtures/estrutura_v7_109_1506.json
import fs from 'node:fs';

const html = fs.readFileSync(
  new URL('../assets/calc-edificio-109_1506-v7-steel.html', import.meta.url), 'utf8');
const blocos = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);

// stub de DOM: qualquer acesso vira no-op encadeável
const noop = new Proxy(function () {}, {
  get: () => noop, set: () => true, apply: () => noop, construct: () => noop,
});
globalThis.document = noop;
globalThis.window = globalThis;
globalThis.localStorage = noop;
globalThis.addEventListener = () => {};
globalThis.requestAnimationFrame = () => 0;
globalThis.THREE = noop;

// Keywords para converter `const` em atribuições globais
const varMapping = {
  'LSF_DB': true,
  'PD': true,
  'NIV': true,
  'W_T': true,
  'W_S': true,
  'STAIRS': true,
  'CX': true,
  'CZ': true,
  'FF': true,
  'LAMINADO': true,
  'CARGAS': true,
  'SEC_Ue250': true,
  'REGRAS_SIS': true,
  'PROJECT': true,
  'BUILDING': true,
  'GRUPO_PAV': true,
};

// Transforma `const/let name = ...` em `globalThis.name = ...` para vars esperadas
// Invariant: each mapped name must have exactly one top-level declaration.
// The regex is un-anchored to find assignments anywhere in the code (block structure varies).
const transformCode = (code) => {
  let result = code;
  for (const varName of Object.keys(varMapping)) {
    // Count occurrences to enforce uniqueness invariant
    const pattern = new RegExp(`\\b(?:const|let)\\s+${varName}\\s*=`, 'g');
    const matches = code.match(pattern) || [];
    if (matches.length > 1) {
      throw new Error(`Invariant violation: ${varName} declared ${matches.length} times, expected exactly 1`);
    }
    // Replace: const/let NAME = ... with globalThis.NAME = ...
    result = result.replace(
      pattern,
      `globalThis.${varName} = `
    );
  }
  return result;
};

// Eval each block with transformation and error handling
for (const b of blocos) {
  try {
    const transformed = transformCode(b);
    (0, eval)(transformed);
  } catch (e) {
    // blocos de UI podem falhar; engine não
  }
}

// Fail-fast: all mapped names must load (derived from varMapping + engine-only names)
const requiredNames = [...Object.keys(varMapping), 'wallToP', 'gerarPecas', 'nestingCorte'];
for (const nome of requiredNames) {
  if (typeof globalThis[nome] === 'undefined') {
    console.error(`engine incompleto: ${nome} não carregou`);
    process.exit(1);
  }
}

const { LSF_DB, W_T, W_S, PD, NIV, wallToP, gerarPecas, nestingCorte } = globalThis;

// wallToP já converteu {t,ab} → P.aberturas com alt/peitoril resolvidos; o gerador
// só distingue JANELA vs não-JANELA, então todo não-janela vira PORTA
function aberturasVao(P) {
  return P.aberturas.map(a => ({
    tipo: a.tipo === 'janela' ? 'JANELA' : 'PORTA',
    posicao_m: a.x, largura_m: a.larg, altura_m: a.alt,
    peitoril_m: a.tipo === 'janela' ? (a.peitoril ?? 1.0) : 0,
  }));
}

const paredes = [];
const todas = [];
const fatias = [{ walls: W_T, fi: 0 }, { walls: W_S, fi: 1 }, { walls: W_S, fi: 2 }];
for (const { walls, fi } of fatias) {
  for (const w of walls) {
    const P = wallToP(w, fi);
    const res = gerarPecas(P);
    if (res.erro) { console.error(`parede ${w.id}: ${res.erro}`); process.exit(1); }
    const porTipo = {};
    let ml = 0, kg = 0;
    for (const p of res.pecas) {
      porTipo[p.tipo] = (porTipo[p.tipo] || 0) + 1;
      ml += p.comp;
      kg += p.comp * (LSF_DB.perfis[p.perfil]?.massaKgM || 0);
      todas.push({ perfil: p.perfil, comp: p.comp });
    }
    paredes.push({
      id: `${fi}/${w.id}`, pav: fi,
      a: w.a, b: w.b, externa: w.t === 'ext' ? 1 : 0, est: w.est ? 1 : 0,
      perfil: P.perfil,
      aberturas: aberturasVao(P),
      ref: { pecas_por_tipo: porTipo, ml: +ml.toFixed(2), kg: +kg.toFixed(2),
             alertas: res.warns.length, n_paineis: res.nPaineis, juntas: res.juntas },
    });
  }
}

const plano = nestingCorte(todas, LSF_DB, 'solto');
let kgLiq = 0, kgComp = 0;
for (const p of plano) {
  kgLiq += p.kg;
  kgComp += p.barras * 6 * (LSF_DB.perfis[p.perfil]?.massaKgM || 0);
}

process.stdout.write(JSON.stringify({
  origem: 'assets/calc-edificio-109_1506-v7-steel.html — gerarPecas headless (paredes)',
  pe_direito_m: PD, niveis: NIV,
  paredes,
  total_paredes: { kg_liquido: +kgLiq.toFixed(0), kg_comprado: +kgComp.toFixed(0) },
}, null, 1));
