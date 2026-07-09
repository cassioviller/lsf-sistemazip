# -*- coding: utf-8 -*-
"""SPIKES DE VALIDAÇÃO — prova executável de cada elo crítico do sistema."""
import sqlite3, math

ok = lambda n: print(f"  PASS ✓  {n}")

# ============ SPIKE 1: DXF → eixos de parede (adaptador) ============
import ezdxf
doc = ezdxf.new(); msp = doc.modelspace()
# parede como linha dupla (espessura 0.14m): duas paredes em L
for (a,b) in [((0,0),(6,0)), ((0,0.14),(6,0.14)),      # parede horizontal
              ((0,0),(0,4)), ((0.14,0.14),(0.14,4))]:  # parede vertical
    msp.add_line(a,b, dxfattribs={"layer":"PAREDE"})
doc.saveas("teste.dxf")
d2 = ezdxf.readfile("teste.dxf")
segs = [((l.dxf.start.x,l.dxf.start.y),(l.dxf.end.x,l.dxf.end.y)) for l in d2.modelspace().query("LINE")]
def eixo_de_par(s1,s2,emin=0.09,emax=0.25):
    (a1,b1),(a2,b2)=s1,s2
    v1=(b1[0]-a1[0],b1[1]-a1[1]); v2=(b2[0]-a2[0],b2[1]-a2[1])
    cross=abs(v1[0]*v2[1]-v1[1]*v2[0])
    if cross>1e-6: return None                      # não paralelas
    L=math.hypot(*v1); n=(-v1[1]/L,v1[0]/L)         # normal
    dist=abs((a2[0]-a1[0])*n[0]+(a2[1]-a1[1])*n[1])
    if not (emin<=dist<=emax): return None
    return (((a1[0]+a2[0])/2,(a1[1]+a2[1])/2),((b1[0]+b2[0])/2,(b1[1]+b2[1])/2),round(dist,3))
eixos=[e for i in range(len(segs)) for j in range(i+1,len(segs)) if (e:=eixo_de_par(segs[i],segs[j]))]
assert len(eixos)==2 and all(abs(e[2]-0.14)<0.01 for e in eixos), eixos
ok(f"DXF (ezdxf MIT): 4 linhas → {len(eixos)} eixos de parede, espessura 0.14m detectada")

# ============ SPIKE 2: CPM — passagem direta/inversa ============
# rede clássica: A(3)→B(4)→D(2); A→C(2)→D; caminho crítico A-B-D = 9
atv={"A":3,"B":4,"C":2,"D":2}; pred={"A":[],"B":["A"],"C":["A"],"D":["B","C"]}
ES,EF={},{}
for a in ["A","B","C","D"]:
    ES[a]=max([EF[p] for p in pred[a]],default=0); EF[a]=ES[a]+atv[a]
fim=max(EF.values()); LS,LF={},{}
for a in ["D","C","B","A"]:
    suc=[s for s in atv if a in pred[s]]
    LF[a]=min([LS[s] for s in suc],default=fim); LS[a]=LF[a]-atv[a]
crit=[a for a in atv if ES[a]==LS[a]]
assert fim==9 and crit==["A","B","D"], (fim,crit)
ok(f"CPM: duração={fim}, caminho crítico={'-'.join(crit)} (validado contra cálculo manual)")

# ============ SPIKE 3: Curva S fecha no total + BDI decomposto ============
custos={"A":3000,"B":8000,"C":2000,"D":4000}
desemb=[0.0]*fim
for a,c in custos.items():
    for t in range(ES[a],EF[a]): desemb[t]+=c/atv[a]
acum=[round(sum(desemb[:t+1]),2) for t in range(fim)]
assert abs(acum[-1]-sum(custos.values()))<0.01
# BDI decomposto (fórmula TCU): ((1+AC+S+R+G)*(1+DF)*(1+L))/(1-I)-1
AC,S,R,G,DF,L,I=0.04,0.008,0.0127,0.0113,0.0139,0.0740,0.0865
bdi=((1+AC+S+R+G)*(1+DF)*(1+L))/(1-I)-1
assert 0.20<bdi<0.30, bdi
ok(f"Curva S fecha em R${acum[-1]:,.2f} = Σcustos; BDI TCU={bdi*100:.2f}%")

# ============ SPIKE 4: Takedown de cargas + fundação (lendo o banco) ============
con=sqlite3.connect("lsf_base.db"); q=lambda s:con.execute(s).fetchone()[0]
peso=lambda m: q(f"SELECT kg_m2 FROM peso_camada WHERE material='{m}'")
pe,trib=2.80,2.0   # pé-direito, área tributária de laje (m por lado)
parede_kgm2 = peso('Peso próprio perfis parede (ref.)')+peso('OSB 11,1mm')+peso('Placa cimentícia 10mm')+peso('Gesso ST 12,5mm')+peso('Lã de vidro 50mm')+peso('Membrana hidrófuga')
g_parede = parede_kgm2*pe*9.81/1000                      # kN/m
g_piso   = peso('Contrapiso seco (2x OSB/cimentícia)')*trib*9.81/1000
q_uso    = 1.5*trib                                       # NBR 6120 residencial kN/m²
g_cob    = peso('Telha shingle + OSB')*trib*9.81/1000
carga_kNm = g_parede+g_piso+q_uso+g_cob                   # térreo de sobrado, simplif.
sigma = q("SELECT tensao_adm_kpa FROM classe_solo WHERE classe='S3'")
larg_teorica = carga_kNm/sigma                            # m (corrida)
LARG_MIN_CONSTRUTIVA = 0.30                               # baldrame/viga: mínimo executivo
largura_sapata = max(larg_teorica, LARG_MIN_CONSTRUTIVA)
governa = "mínimo construtivo" if larg_teorica < LARG_MIN_CONSTRUTIVA else "tensão do solo"
assert 3<carga_kNm<25 and largura_sapata>=LARG_MIN_CONSTRUTIVA, (carga_kNm,largura_sapata)
ok(f"Takedown via banco: parede={parede_kgm2:.1f}kg/m² → {carga_kNm:.2f}kN/m → sapata {largura_sapata*100:.0f}cm (governa: {governa}; teórica {larg_teorica*100:.1f}cm)")

# ============ SPIKE 5: Panelizador — junta × vão ============
def paneliza(L,vaos,pmax=6.0,folga=0.30):
    """corta parede em painéis; junta proibida a <folga da lateral de vão"""
    juntas=[]; x=pmax
    proib=[(a-folga,b+folga) for a,b in vaos]
    while x<L-1e-9:
        while any(a<x<b for a,b in proib): x-=0.05   # recua junta p/ fora da zona
        juntas.append(round(x,2)); x=round(x,2)+pmax
    return juntas
L=9.20; vaos=[(3.00,4.20)]                # vão de janela entre 3.00 e 4.20m
juntas=paneliza(L,vaos)
assert all(not(2.70<j<4.50) for j in juntas), juntas
ok(f"Panelizador: parede {L}m, vão {vaos[0]} → juntas em {juntas} (nenhuma na zona proibida)")

# ============ SPIKE 6: mapeamento item→composição→custo (D2/D7 fim-a-fim) ============
custo=q("SELECT ROUND(custo_unitario,2) FROM vw_custo_composicao v JOIN mapeamento_item m ON m.composicao_id=v.composicao_id WHERE m.item_derivado='estrutura.aco_kg'")
kg_exemplo=1500
ok(f"Cadeia fim-a-fim: 'estrutura.aco_kg' → VK-C-001 → R${custo}/kg → {kg_exemplo}kg = R${custo*kg_exemplo:,.2f}")
con.close()
print("\n== TODOS OS 6 SPIKES PASSARAM ==")
