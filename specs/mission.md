# Misión

ImageEngine da a cualquier agente de IA la capacidad de generar y editar imágenes en local, en el PC de quien lo usa, sin servicios de pago ni envío de datos a terceros.

## Objetivo de distribución

Una persona sin conocimientos de Python ni de ComfyUI debe poder pasar de "no tengo nada" a "mi agente ha generado una imagen":

- con **un solo comando**, o pidiéndoselo a su agente;
- en **Linux, macOS o Windows**;
- con **cualquier agente o editor compatible con MCP**, incluidos los que usan modelos de lenguaje locales (opencode, Hermes, pi), Codex, Claude, Cursor, VS Code e IntelliJ;
- **compaginándolo con sus modelos locales** en la misma GPU, sin que tenga que liberar memoria a mano;
- sabiendo **antes de descargar** cuánto ocupa, qué licencias acepta y qué rendimiento esperar de su hardware.

## Criterios de éxito de la v1

1. En una máquina limpia con GPU compatible, la instalación termina sin intervención salvo aceptar las licencias y elegir un perfil.
2. La primera imagen se genera sin editar a mano ningún archivo de configuración.
3. Si algo falla, `doctor` dice qué falla y cómo arreglarlo.
4. Desinstalar deja el sistema como estaba y nunca borra lo que el usuario ya tenía.
5. Solo se anuncia como soportada una combinación de sistema y GPU que se haya probado con hardware real.

## Fuera de alcance en la v1

- Servicio alojado o generación remota.
- Interfaz gráfica propia: los agentes y la CLI son la interfaz.
- Redistribuir pesos de modelos: siempre se descargan desde su origen.
- Instalar Ollama, LM Studio, llama.cpp o vLLM: son integraciones opcionales y solo se gestionan si ya existen.
