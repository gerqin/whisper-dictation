# Whisper Dictation — Handoff

## Qué es
Dictado por voz local en macOS usando whisper-cpp (large-v3-turbo). Toggle con hotkey: graba → transcribe → pega.

## Estado actual: FUNCIONAL
- Dictado funciona end-to-end
- Server corre como daemon (launchd), se inicia solo al bootear
- Modelo en RAM (~2GB permanentes)
- Repo en GitHub: https://github.com/gerqin/whisper-dictation

## Arquitectura

```
Hotkey (⌘⌘ en Raycast)
  → dictate.sh (Raycast script command, mode silent)
    → whisper-toggle.sh
      Primera vez: touch marker + sox graba en background
      Segunda vez: detecta marker → pkill sox → curl localhost:8787 → pbcopy + ⌘V paste
```

### Componentes
| Componente | Path | Rol |
|---|---|---|
| whisper-server | daemon en port 8787 | Modelo en RAM, acepta audio por HTTP |
| whisper-toggle.sh | ~/Dev/whisper-dictation/ | Toggle start/stop + transcribe + paste |
| dictate.sh | ~/Dev/whisper-dictation/ | Raycast script command wrapper |
| install.sh | ~/Dev/whisper-dictation/ | Instalador portable |
| uninstall.sh | ~/Dev/whisper-dictation/ | Desinstalador |
| launchd plist | ~/Library/LaunchAgents/com.local.whisper-server.plist | Daemon config |
| modelo | ~/.local/share/whisper-models/ggml-large-v3-turbo.bin | 1.5GB |

### Dependencias (brew)
- whisper-cpp (incluye whisper-server, whisper-cli)
- sox (grabación de audio)

## Comportamiento conocido
- En Claude Code: pega como `[Pasted text +N lines]` — el texto llega completo, solo la UI lo muestra colapsado
- `language=auto` — detecta español, inglés, y mezcla
- sox graba hasta que se mata con pkill — sin timeout

## Operaciones
```bash
# Parar server (liberar 2GB RAM)
launchctl unload ~/Library/LaunchAgents/com.local.whisper-server.plist

# Iniciar server
launchctl load ~/Library/LaunchAgents/com.local.whisper-server.plist

# Verificar que está corriendo
curl -s http://127.0.0.1:8787/health

# Cambiar modelo: editar plist, cambiar -m path, reload
```

## Pendiente: Menu bar app
El usuario quiere una app de menu bar (barra de estado macOS) para:
- Ver si el server está corriendo (indicador visual)
- Start/Stop server
- Cambiar modelo (listar modelos disponibles en ~/.local/share/whisper-models/)
- Posiblemente ver RAM usage

### Plan de implementación
- **Framework:** Python + rumps (pip install rumps)
- **Archivo:** ~/Dev/whisper-dictation/menubar.py
- **Funcionalidad:**
  - Ícono en menu bar (🎙 verde = running, rojo = stopped)
  - Menu items: Status, Start Server, Stop Server, separator, Models submenu, separator, Quit
  - Start/Stop llama `launchctl load/unload` del plist
  - Status checa `curl localhost:8787/health`
  - Models submenu lista archivos *.bin en ~/.local/share/whisper-models/
  - Cambiar modelo: edita el plist, reload daemon
- **Empaque:** py2app o simplemente correr con python, agregar a Login Items
- **Agregar a install.sh:** pip install rumps, crear Launch Agent para menubar también

### Archivos a crear/modificar
- `menubar.py` — app principal
- `requirements.txt` — rumps
- `install.sh` — agregar instalación de menubar
- `com.local.whisper-menubar.plist` — Launch Agent para auto-start del menubar
