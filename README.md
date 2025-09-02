# Orlando Video Plugin

A plugin for [Orlando Toolkit](https://github.com/orsso/orlando-toolkit) that converts video files to DITA topics with in-app preview.

## Features

- Convert video files (MP4, AVI, MOV, WMV, WebM, MKV) to DITA topics
- Custom workflow with file selection or folder structure preservation  
- In-app video preview in the Structure tab (VLC via python-vlc)
- Automatic metadata extraction and display

## Installation

**Via Orlando Toolkit Plugin Manager:**
1. Open Plugin Management from Orlando Toolkit splash screen
2. Enter this repository URL: `https://github.com/orsso/orlando-video-plugin`
3. Click "Import Plugin" to install
4. Activate the plugin

**Optional for preview**: Install VLC media player

## Usage

**File Selection**: Choose individual video files → converts to separate DITA topics  
**Folder Selection**: Process entire directory → preserves folder hierarchy as DITA sections

```
Videos/
├── Training/          → <topichead navtitle="Training">
│   ├── intro.mp4     →   <topicref href="topics/intro.dita"/>
│   └── advanced.mp4  →   <topicref href="topics/advanced.dita"/>
└── Demos/            → <topichead navtitle="Demos">
    └── demo1.mp4     →   <topicref href="topics/demo1.dita"/>
```

**Preview**: Video Preview panel in Structure tab with playback controls

## Output

- **DITA Topics**: One `.dita` concept file per video with embedded `<object>` elements
- **Media Files**: Videos saved to `DATA/media/` directory
- **Metadata Tables**: Duration, resolution, file size, format automatically extracted

## Requirements

- [Orlando Toolkit](https://github.com/orsso/orlando-toolkit) 1.é.0+
- Python 3.8+
- VLC media player (optional, for preview)
