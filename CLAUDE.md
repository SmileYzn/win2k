# Win2k — tema Windows 2000 para XFCE

Tema completo (GTK 2/3/4, xfwm4, ícones, cursores, sons, menu Iniciar, painel) derivado do
Chicago95/SE98. Repositório: https://github.com/SmileYzn/win2k

## Idioma e estilo

- Responder ao usuário em português do Brasil.
- Textos de interface (instalador, menu, ferramentas): pt-BR, com `Name[pt_BR]` nos `.desktop`.
- Comentários: seguir o arquivo. CSS e `.menu` estão em inglês; os scripts Python, em português.
- CSS GTK3 do tema: indentação de 2 espaços, seletores relacionados empilhados (ver as notas no topo de cada arquivo).

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `Theme/Win2k` | `gtk-2.0`, `gtk-3.0` (+ links `gtk-3.22`, `gtk-3.24`), `gtk-4.0`, `xfwm4`, `xfwm4_hidpi`, `openbox-3`, `metacity-1`, `cinnamon`, `gnome-shell`, `xfce-notify-4.0` |
| `Icon/Win2k` | Pacote de ícones (~32 mil PNGs, ~25 mil links), GPL-2.0 (`Icon/Win2k/LICENSE`). `icones.html` é gerado por `tools/icon-gallery.py`. Sincronizado com o SE98 (github.com/nestoris/Win98SE, pasta `SE98`) até o commit `a837b57a`: na próxima sincronização, aplicar `git diff a837b57a HEAD -- SE98` com `git apply -p2 --directory=Icon/Win2k` e depois rodar `tools/xsi-links.py` |
| `Cursor/Win2k_Cursors` | Cursores |
| `Sound/Win2k`, `Sound/Win2k-Utopia` | Temas de sons freedesktop (`stereo/*.wav`): esquemas "Padrão do Windows" e "Utopia" (este herda do Win2k), extraídos de `I386/*.WA_` da instalação do Windows 2000 (mapeamentos em `HIVEDEF.INF` e `MMOPT.INF`). `win2k-logon-sound.desktop`: autostart do som de logon no XFCE e no MATE (o Cinnamon usa `org.cinnamon.sounds`). No instalador, componentes `sounds` e `sounds-utopia` (`SOUND_THEMES`): só um fica ativo (`state.json` → `sounds_applied`) |
| `Wallpaper/Win2k` | Papéis de parede |
| `Menu` | `win2k-start.menu` (plugin "Menu de aplicativos"), `applications/`, `desktop-directories/`, `win2k-logoff.py` |
| `Panel/win2k.tar.bz2` | Perfil do xfce4-panel-profiles |
| `Panel/mate-win2k.dconf` | Painel do MATE (dconf de `/org/mate/panel/`, sem `history-mate-run`, posições presas à direita) |
| `Setup` | `win2k-installer.py` (assistente + CLI) e imagens do assistente |
| `tools` | `win2k-sounds.py` (testador de sons), `icon-gallery.py`, `xsi-links.py` (links `xsi-*` do xapp-symbolic-icons; gera `xsi-faltantes.md`) |
| `Screenshots` | Capturas usadas no README |

## Instalador (`Setup/win2k-installer.py`)

- `SRC` é a raiz do projeto (o script fica em `Setup/`).
- `COMPONENTS` define origem e destino de cada componente nos modos `user` e `system`. Para um componente novo, basta acrescentar uma entrada ali.
- Modo sistema: o próprio script é chamado de novo com `pkexec ... --root install|uninstall <comps>`. O lado root só aceita nomes de `COMPONENTS` e destinos fixos. Não aceitar caminhos vindos da linha de comando.
- "Aplicar" grava pelo `xfconf-query` (XFCE) e pelo `gsettings` (Cinnamon, `cinnamon_settings_for`), cada um só se a área de trabalho estiver instalada (`have_xfce`, `have_cinnamon`, `have_mate_panel`), e guarda o valor anterior em `~/.local/share/win2k-installer/state.json`. Sem a ferramenta na remoção, o valor fica guardado. A desinstalação restaura esses valores, o `~/.config/gtk-4.0` e o painel salvo.
- No modo usuário, `fix_menu_paths` troca `/usr/share/win2k-menu` pelo destino real nos `.desktop` do menu.
- A janela força o tema e os ícones do projeto (`use_project_theme`: links `Win2k-Setup` num diretório temporário + `GTK_THEME`). Os subprocessos recebem `CHILD_ENV`, o ambiente original.
- GTK 3: sempre `gi.require_version("Gdk", "3.0")` junto com o Gtk, senão o Gdk 4 é carregado.

## Armadilhas conhecidas

- **Ícones `xsi-*`** (xapp-symbolic-icons, usados pelo Cinnamon, Nemo, Xed e XApps): são links gerados por `tools/xsi-links.py --xsi <clone do xapp-symbolic-icons>`, a partir da tabela `icons/xsi-adwaita-symbolic.info` do XSI e da tabela `MANUAL` do script. Não editar à mão: rodar o script de novo (ele apaga e refaz todos os links `xsi-*`) depois de sincronizar com o SE98 ou de atualizar o XSI. Cada link fica na pasta do ícone de destino e só é criado se ele existir (o PR #51 do Win98SE foi revertido por links quebrados). O script também cria `nome-symbolic` → `nome` para os ícones que só existem coloridos no Win2k mas têm versão simbólica nos temas herdados (o Cinnamon pede notificações e applets como simbólicos e, sem isso, mostra o desenho do Adwaita/breeze); esses links ficam listados em `tools/symbolic-links.txt`, que o script usa para apagá-los ao rodar de novo.
- **Apps libadwaita/GTK 4** só leem o tema em `~/.config/gtk-4.0`. Depois de mexer em `gtk-4.0`, sincronizar com `cp -r Theme/Win2k/gtk-4.0/. ~/.config/gtk-4.0/`. O instalador faz isso ao aplicar o tema.
- **gtk-4.0 é independente**: os assets ficam em `gtk-4.0/assets` (não referenciar `../gtk-3.0`).
- **Menus de contexto** herdam o CSS do widget que os abre (fonte monoespaçada do editor). Por isso existe `font: initial` em `menu`/`.context-menu` (GTK 3) e em `popover.background` (GTK 4).
- **Painel XFCE**: o widget do plugin (`#separator-N`, `#showdesktop-N`) não desenha nada, então a estilização vai nos filhos (`> box`, `#showdesktop-button`). Os IDs de plugin variam com o layout; os hacks ficam em `gtk-3.0/apps/xfce-panel-hacks.css`.
- **Separadores do painel**: os estilos "separador" e "alça" do xfce4-panel são desenhados em cairo e não aceitam tema. A alça Win2k vem de `assets/panel-handle*.png` via `border-image`.
- **Menu Iniciar**: o painel monitora o arquivo `.menu`. Se ele sumir por alguns segundos, aparece "Falha ao carregar o menu de aplicativos". Apagar e copiar em sequência e reiniciar o painel depois.
- **xfwm4**: o degradê da barra de título usa `title-*-stretch.png` (2048 px). O Openbox só aceita `.xbm`.
- **Cursor errado em apps Java**: `XCURSOR_THEME` em `/etc/environment` ou `~/.profile` tem prioridade.
- **Thunar 4.20**: a seleção arredondada vem do próprio Thunar (`/misc-highlighting-enabled`), não do tema.

## Testes sem mexer no sistema do usuário

- O assistente não tem sudo. Instalação no sistema: o usuário roda `python3 Setup/win2k-installer.py --system`.
- Se faltar uma ferramenta do sistema (xdotool, wmctrl, PIL etc.), avisar o usuário: ele instala. Não contornar em silêncio.
- **Nunca** usar `pkill -f` (casa com o próprio shell); matar pelos PIDs.
- Capturas: nunca da tela real do usuário (ela tem dados pessoais). Usar só a janela de teste.
- Janelas GTK isoladas: `Xephyr :5 -screen 1024x768 -ac` + `env -u DBUS_SESSION_BUS_ADDRESS DISPLAY=:5`. Cliques e teclas com `xdotool`, janelas com `wmctrl` (ou `xdotool`), sempre com `DISPLAY=:5`. Medição de pixels com PIL (`python-pillow`).
- Tema do projeto sem instalar: link `themes/Win2k` → `Theme/Win2k` num diretório colocado no começo do `XDG_DATA_DIRS`, + `GTK_THEME=Win2k`.
- Sessão XFCE completa isolada (para capturas): `dbus-run-session` com `XDG_CONFIG_HOME`/`HOME` de demonstração (cópias dos canais xfconf) rodando xfsettingsd, xfwm4, xfdesktop e xfce4-panel no Xephyr. Sempre com o compositor ligado (`xfwm4 --compositor=on`), como no sistema do usuário: sem ele, o GTK 3 não dá decoração CSD aos menus e eles aparecem sem moldura. Para caminho e usuário genéricos: `unshare --user --map-root-user --mount --uts`, tmpfs em `/home`, bind de `/home/usuario` e de um `/etc/passwd` falso, depois `unshare --user --map-user=1000 --map-group=1000`.
- **Isolamento da sessão de teste**: exportar `HOME`/`XDG_CONFIG_HOME`/`XDG_CACHE_HOME` de teste *antes* do `dbus-run-session` (o dconf-service é ativado pelo barramento e herda o ambiente dele; senão grava no dconf real) e remover `SESSION_MANAGER` (`env -u SESSION_MANAGER`), senão painéis e gerenciadores de janela se registram no xfce4-session real e, ao serem encerrados, são reiniciados na tela do usuário. Conferir em `/proc/PID/environ` antes de testar.
- Tela de login: `lightdm --test-mode --config <conf>` dentro desse namespace, com um `Xephyr` intermediário no `PATH` para definir `-screen`.
- Instalador sem efeitos reais: `HOME` falso + `xfconf-query`, `xfce4-panel` e `xfce4-panel-profiles` falsos no `PATH`.

## Recursos da Microsoft

Sons (os dois esquemas), cursores, imagens do Setup (`Setup/*.png`) e faixas do menu foram extraídos de uma ISO do Windows 2000. São da Microsoft. Não acrescentar outros sem avisar o usuário.
