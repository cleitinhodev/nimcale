<p align="center">
  <img src="nimcale/assets/icons/nimcale_icon_512.png" width="160" alt="Nimcale">
</p>

<h1 align="center">Nimcale</h1>

<p align="center">
  <b>Transforme uma imagem + mapa de altura em um relevo 3D pronto para imprimir:</b><br>
  moedas, medalhas, placas, azulejos e recortes — com exportação HD fechada (watertight).
</p>

<p align="center">
  <a href="https://github.com/cleitinhodev/nimcale/releases/latest"><img alt="Versão estável" src="https://img.shields.io/github/v/release/cleitinhodev/nimcale?label=vers%C3%A3o%20est%C3%A1vel&color=a855f7"></a>
  <a href="https://github.com/cleitinhodev/nimcale/releases"><img alt="Downloads" src="https://img.shields.io/github/downloads/cleitinhodev/nimcale/total?color=ec4899"></a>
  <a href="https://github.com/cleitinhodev/nimcale/actions/workflows/build.yml"><img alt="Build" src="https://github.com/cleitinhodev/nimcale/actions/workflows/build.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="GPL-3.0" src="https://img.shields.io/badge/licen%C3%A7a-GPL--3.0-ec4899"></a>
  <img alt="Windows | Linux" src="https://img.shields.io/badge/Windows%20%7C%20Linux-OpenGL%203.3-7c3aed">
</p>

<p align="center">
  <a href="https://www.bugzinho.com/">Site</a> ·
  <a href="https://github.com/cleitinhodev/nimcale">Projeto</a> ·
  <a href="https://www.bugzinho.com/donate">Doar 💜</a> ·
  <a href="#english">English</a>
</p>

![Nimcale](docs/screenshots/main.png)

## ✨ Recursos

- **Relevo a partir de imagens** — textura colorida + mapa de altura (branco = alto, preto = baixo).
  Profundidade, espessura da base, suavização, limiar, brilho, contraste, níveis, curva de altura (gama),
  inverter, ruído e realce de detalhes.
- **Formas** — placa inteira ou **recorte do objeto**; contornos: contorno da imagem, círculo, elipse,
  retângulo arredondado, hexágono, octógono; **borda** (aro de moeda) e **chanfro**.
  Predefinições: moeda, medalha, placa, contorno, azulejo.
- **Recorte automático** — ao importar uma imagem nova o contorno segue o objeto (não fica redondo):
  fundo escuro, branco, transparente ou uma cor escolhida é detectado sozinho; o contorno pode vir do mapa
  de altura, da transparência ou da cor da textura. Ajuste fino: limiar/tolerância, expandir/encolher,
  suavizar, maciez da borda, preencher buracos, remover ilhas pequenas, manter só o maior objeto e
  **prévia do contorno** ao vivo.
- **Textura** — ajuste (esticar/conter/preencher), escala, deslocamento, rotação e **alinhamento automático**;
  visualização textura / altura / **mistura**; salvar e carregar alinhamento (compatível com o placa3d).
- **Modelagem** — pincéis de escultura (elevar, rebaixar, suavizar, aplainar, apagar), **desfazer/refazer**,
  espelhar, girar 90°, recortar, medidas reais em **mm** (volume e peso em PLA/prata/ouro), cotas, grade, giro automático.
- **Exportação** — STL (binário/ASCII), OBJ + MTL + textura, GLB / glTF, PLY com cores, **3MF**, OFF,
  mapa de altura PNG 16 bits, normal map, textura PNG, **GIF** girando e capturas de tela HD / transparentes.
- **Exportação HD** — malha densa independente da prévia (até 6144 amostras no lado maior, milhões de
  triângulos), reamostragem bicúbica, progresso com cancelamento, **sólido fechado verificado** e simplificação adaptativa opcional.
- **Projetos** `.nimcale`, arquivos recentes, **arrastar e soltar** imagens.
- **Interface** moderna (Dear ImGui com docking): menus, barra de ferramentas, abas, inspetor, barra de status,
  tema roxo/rosa com **neon e gradientes animados** (podem ser desligados) e **barra de título que acompanha
  o tema claro/escuro do sistema** (ou escura / clara / cor do tema).
- **12 idiomas** com detecção automática: Português (Brasil), English, Español, Français, Deutsch, Italiano,
  Русский, Polski, Türkçe, 简体中文, 日本語, 한국어.
- **Compatibilidade máxima** — OpenGL 3.3; se o driver de vídeo falhar, o Nimcale usa automaticamente o
  renderizador por software **Mesa llvmpipe** incluído (funciona até em PCs/VMs sem GPU).

| | | |
|---|---|---|
| ![Medalha](docs/screenshots/medal_gold.png) | ![Exportar](docs/screenshots/export.png) | ![Escultura](docs/screenshots/sculpt.png) |
| ![Recorte](docs/screenshots/shape_cutout.png) | ![Sobre](docs/screenshots/about.png) | ![日本語](docs/screenshots/lang_ja.png) |

## 🧪 Versão de teste (beta): Importar superfície

> ⚠️ **Experimental.** A versão estável continua sendo a **1.0.3** (branch `main`). A versão de teste
> **1.1.0-beta.1** é publicada como *pré-lançamento* a partir do branch `dev/surface` e mostra o selo
> "VERSÃO DE TESTE" no app.

A nova aba **Superfície** aplica a textura **e** o relevo atuais sobre um objeto 3D (copo, garrafa, caixa...),
sem remover nenhuma opção existente. Ao abrir, o app continua mostrando a moeda padrão, sem superfície.

- **Formatos:** OBJ (+MTL), STL, PLY, GLB/glTF, 3MF, OFF e DAE (Collada). FBX **não** é suportado.
- **12 modelos de exemplo:** copo, caneca com alça, garrafa, vaso, bola, caixa, lata, prato, chaveiro,
  placa tipo capinha, porta-canetas e cúpula de luminária.
- Projeções automática, UV do modelo, cilíndrica, esférica, plana, caixa (triplanar) e decalque; ajuste,
  posição, escala, proporção X/Y, rotação, emenda, repetir, espelhar, máscara pelo recorte da placa.
- Relevo deslocando a superfície pelas normais com subdivisão adaptativa; exportação tudo mesclado
  (STL, OBJ, GLB/glTF, PLY, 3MF, OFF, também em HD), fechado se o modelo original for fechado.
- **Remover superfície / voltar à placa padrão** com um clique (desfazível), mantendo todos os ajustes.

| Caneca | Caixa (repetir) |
|---|---|
| ![Caneca](docs/screenshots/surface_mug.png) | ![Caixa](docs/screenshots/surface_box.png) |

## 📥 Download (Windows)

Baixe o `Nimcale-<versão>-windows-x64.zip` da **[versão estável mais recente](https://github.com/cleitinhodev/nimcale/releases/latest)**,
extraia a pasta e execute **`Nimcale.exe`**. Não precisa instalar nada.

> O executável ainda não é assinado digitalmente: se o Windows SmartScreen avisar, clique em
> *Mais informações → Executar assim mesmo*.

Configurações e log ficam em `%APPDATA%\Nimcale` (no Linux: `~/.config/Nimcale`).

## ⌨️ Atalhos principais

| Tecla | Ação | Tecla | Ação |
|---|---|---|---|
| Ctrl+O | importar textura + mapa | Ctrl+Shift+O | abrir projeto |
| Ctrl+T / Ctrl+M | importar textura / mapa de altura | Ctrl+S / Ctrl+Shift+S | salvar projeto |
| Ctrl+E | janela de exportação | Ctrl+Shift+E | STL HD rápido |
| Ctrl+Z / Ctrl+Y | desfazer / refazer | Ctrl+Q | **sair** |
| T | textura / altura / mistura | B | placa / recorte do objeto |
| F | wireframe | U | iluminação |
| K | modo escultura | Espaço | giro automático |
| 1 2 3 4 | vistas frente / iso / lado / topo | Ctrl+R | redefinir câmera |
| + / − | profundidade do relevo | 9 / 0 | espessura da base |
| [ / ] | limiar do recorte | , / . | suavização |
| ← → ↑ ↓ | direção / elevação da luz | W A S D, Q/E, Z/X, C/V | mover / escalar textura |
| G / Ctrl+L | salvar / carregar alinhamento | P / Ctrl+P | captura / captura como |
| R | redefinir tudo | Tab | mostrar/ocultar painéis |
| F1 | ajuda | F11 | tela cheia |
| Esc | fechar janela / sair da escultura | Shift | ajuste fino |

Mouse: arrastar com o esquerdo gira, direito/meio move, roda dá zoom; no modo escultura o esquerdo pinta
(Shift inverte) e Ctrl+roda muda o tamanho do pincel.

> **Mudança em relação ao placa3d:** `Esc` não fecha mais o programa — use **Ctrl+Q**.

## 🛠️ Rodar a partir do código

```bash
git clone https://github.com/cleitinhodev/nimcale.git
cd nimcale
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m nimcale                       # moeda padrão
python -m nimcale textura.png altura.png
python -m nimcale projeto.nimcale
```

Opções úteis: `--software` (força o renderizador Mesa), `--gpu`, `--lang en`, `--reset-layout`,
`--selftest`, `--shot arquivo.png` (captura de tela e sai), `--version`.

### Testes

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Os testes cobrem o pipeline do relevo, malhas fechadas para todas as formas, todos os formatos de exportação
(verificados com `trimesh`), a exportação HD (milhões de triângulos, sólido fechado), escultura, desfazer/refazer,
idiomas completos e configurações.

### Gerar o executável do Windows

- **No Windows:** `.\scripts\build_windows.ps1` (precisa do Python 3.10–3.13 e do 7-Zip).
- **No Linux com Wine:** `scripts/build_wine.sh` (Python do Windows dentro do Wine, ver o script).
- **GitHub Actions:** cada push compila e testa no `windows-latest`; ao enviar uma tag `v*` o zip é anexado ao release.

O build usa PyInstaller (`nimcale.spec`) e baixa o Mesa llvmpipe com `scripts/fetch_mesa.py`.

## 📁 Estrutura

```
nimcale/
  core/      imagens, parâmetros, pipeline do relevo, formas, malha fechada, alinhamento
  export/    escritores STL/OBJ/GLB/PLY/3MF/OFF/PNG e o trabalho de exportação HD
  tools/     histórico (desfazer/refazer) e escultura
  render/    câmera, shaders e renderizador moderngl
  ui/        tema, fontes, painéis, janelas, viewport, menus/barra de ferramentas
  i18n/      traduções (locales/*.json)
  assets/    ícones, fontes, moeda padrão
scripts/     build, fontes, ícones, Mesa, verificação de traduções
tests/       testes pytest
```

Para adicionar um idioma: copie `nimcale/i18n/locales/en.json`, traduza, registre o código em
`nimcale/i18n/__init__.py` e rode `python scripts/i18n_keys.py --check` (e `scripts/build_fonts.py`
se o idioma usar novos caracteres).

## 📜 Licença

Nimcale é software livre sob a **GNU General Public License v3.0 ou posterior** — veja [LICENSE](LICENSE).
Componentes de terceiros (Dear ImGui, Mesa, fontes Noto, Font Awesome…) estão listados em
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Se o Nimcale foi útil, considere [apoiar o projeto](https://www.bugzinho.com/donate) 💜

---

<a id="english"></a>

## 🇺🇸 English

**Nimcale** turns an image and a height map into a printable 3D relief — coins, medals, plates, tiles and
cut-out shapes — and exports **watertight high-definition meshes**.

**Highlights**

- Relief controls: depth, base thickness, smoothing, threshold, brightness/contrast, levels, gamma curve,
  invert, noise and detail enhancement; cutout shapes (image outline, circle, ellipse, rounded rectangle,
  hexagon, octagon) with rim and bevel; presets (coin, medal, plate, contour, tile).
- Texture fit/scale/offset/rotation, **auto-align**, texture/height/**mix** views, alignment save/load.
- **Automatic cutout** that follows each imported image (dark / white / transparent / picked-colour background,
  height map, texture alpha or texture colour key) with fine tuning and a live outline preview.
- Sculpt brushes (raise, lower, smooth, flatten, erase), undo/redo, mirror, rotate, crop,
  real-world measurements in **mm** (volume, PLA/silver/gold weight), turntable.
- Export to STL (binary/ASCII), OBJ+MTL+texture, GLB/glTF, PLY with colours, **3MF**, OFF, 16-bit height map,
  normal map, texture PNG, turntable **GIF**, HD/transparent screenshots.
- **HD export** independent of the preview (up to 6144 samples on the longest side, millions of triangles),
  bicubic upsampling, progress + cancel, verified closed solid, optional adaptive decimation.
- `.nimcale` projects, recent files, drag & drop.
- Modern docking UI with an animated purple/pink neon theme (can be disabled), a native title bar that follows
  the OS light/dark theme (or dark / light / theme colour), and **12 languages**
  with auto-detection (pt-BR default, English fallback).
- OpenGL 3.3 with automatic fallback to the bundled **Mesa llvmpipe** software renderer.

**Test version (beta) - Import surface:** the pre-release **1.1.0-beta.1** (branch `dev/surface`, marked
as a test build; stable stays **1.0.3**) adds a *Surface* tab that puts the texture and relief onto a 3D
model (OBJ+MTL, STL, PLY, GLB/glTF, 3MF, OFF, DAE; no FBX) with automatic / UV / cylindrical / spherical /
planar / box / decal projection, placement controls, displacement along normals, 12 sample models, merged
watertight export (also HD) and a one-click *Remove surface* that returns to the normal plate.

**Download:** get `Nimcale-<version>-windows-x64.zip` from
[the latest stable release](https://github.com/cleitinhodev/nimcale/releases/latest), extract and run `Nimcale.exe`.

**From source:** `pip install -r requirements.txt` then `python -m nimcale [texture heightmap | project.nimcale]`.
Tests: `pip install -r requirements-dev.txt && python -m pytest`.
Windows build: `scripts/build_windows.ps1`, `scripts/build_wine.sh` or the GitHub Actions workflow.

**Note:** `Esc` no longer quits (it closes windows / leaves sculpt mode). Use **Ctrl+Q** to quit.

**License:** GPL-3.0-or-later. Third-party notices in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Website: <https://www.bugzinho.com/> · Donate: <https://www.bugzinho.com/donate>
