# TubeBatch — instalação direta no Windows

Este projeto roda diretamente no Windows usando:

- Python 3.11 ou superior
- FFmpeg
- FastAPI
- yt-dlp

Não é necessário Docker.

## 1. Instale o Python

Instale o Python 3.11+.

Durante a instalação, marque:

```text
Add Python to PATH
```

Depois confirme no Prompt de Comando:

```bat
python --version
```

## 2. FFmpeg automático

Você **não precisa instalar o FFmpeg manualmente**.

Ao executar:

```text
install.bat
```

o instalador verifica se `ffmpeg/ffmpeg.exe` e `ffmpeg/ffprobe.exe` existem. Se não existirem, ele baixa automaticamente o pacote **FFmpeg Essentials para Windows**, extrai os dois executáveis e salva dentro da própria pasta do TubeBatch.

O sistema usa esse FFmpeg local diretamente, portanto **não é necessário configurar o PATH do Windows**.

## 3. Instale o TubeBatch

Execute:

```text
install.bat
```

O instalador vai:

1. verificar o Python;
2. baixar e instalar automaticamente o FFmpeg portátil, se necessário;
3. criar `.venv`;
4. atualizar o pip;
5. instalar todas as dependências.

## 4. Inicie o site

Execute:

```text
start.bat
```

O navegador abrirá automaticamente em:

```text
http://127.0.0.1:8000
```

Para encerrar o servidor, pressione:

```text
CTRL + C
```

na janela do terminal.

## Atualizar o yt-dlp

Como o YouTube altera o sistema com frequência, incluí:

```text
update.bat
```

Execute esse arquivo sempre que downloads começarem a falhar por alterações do YouTube.

## Recursos

- vídeos normais do YouTube;
- YouTube Shorts;
- vários links no mesmo lote;
- MP4;
- MP3;
- 128 / 192 / 256 / 320 kbps;
- escolha de qualidade;
- melhor qualidade disponível;
- progresso por vídeo;
- downloads simultâneos;
- download individual;
- download do lote em ZIP.

## Estrutura

```text
youtube-batch-downloader/
├── app/
│   ├── main.py
│   └── static/
│       ├── index.html
│       ├── styles.css
│       └── app.js
├── downloads/
├── .env.example
├── install.bat
├── start.bat
├── update.bat
├── requirements.txt
└── README.md
```

## Configuração

Por padrão:

```env
MAX_URLS_PER_BATCH=0
INSPECT_WORKERS=6
DOWNLOAD_WORKERS=3
JOB_TTL_HOURS=12
```

`MAX_URLS_PER_BATCH=0` significa que não há um limite fixo definido pelo programa.

Mesmo assim, a quantidade de downloads simultâneos continua controlada por:

```env
DOWNLOAD_WORKERS=3
```

Isso evita que muitos vídeos sejam processados pelo FFmpeg ao mesmo tempo.

## Observação

Use a ferramenta apenas para conteúdo próprio, de domínio público ou para o qual você possua autorização para baixar.
