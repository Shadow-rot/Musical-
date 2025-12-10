# YouTube Download API

A simple FastAPI service for downloading YouTube videos and audio.

## Features

- Download audio (MP3)
- Download video (MP4, 720p)
- Simple API key authentication
- Fast and efficient

## API Endpoints

### Root
```
GET /
```
Returns API information

### Download Audio
```
GET /song/{video_id}?api=YOUR_KEY
```
Downloads audio from YouTube video

### Download Video
```
GET /video/{video_id}?api=YOUR_KEY
```
Downloads video from YouTube

### Check Status
```
GET /status/{video_id}
```
Check if a video has been downloaded

### Download File
```
GET /download/{filename}
```
Download the processed file

## Environment Variables

- `API_KEY`: API authentication key (default: "shadwo")
- `PORT`: Server port (default: 8000)

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
python app.py
```

## Deploy to Render

1. Push this repository to GitHub
2. Connect your GitHub repo to Render
3. Render will automatically deploy using `render.yaml`

## Usage Example

```bash
# Download audio
curl "https://your-app.onrender.com/song/dQw4w9WgXcQ?api=shadwo"

# Download video
curl "https://your-app.onrender.com/video/dQw4w9WgXcQ?api=shadwo"
```

## License

MIT
