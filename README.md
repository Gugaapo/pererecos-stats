# Pererecos Stats

Real-time Twitch chat statistics dashboard for tracking chat activity and user engagement.

![Preview](frontend/sapo.avif)

## Features

### User Statistics
- **Message count** with percentile ranking
- **Hourly activity chart** showing when users are most active
- **Peak hours** and **favorite hour** detection
- **Rival detection** - finds users with similar activity patterns using cosine similarity
- **Top replies** - who the user responds to most
- **Leaderboard rankings** across all categories
- **Top 10 emotes** used (last 30 days)
- **Recent messages** with 7TV emote rendering

### Leaderboards
- **Top 10** - Most active chatters
- **Rising Stars** - Biggest growth (last 7 days vs previous 7 days)
- **Hour Leaders** - Who dominates each hour of the day
- **Writers** - Longest average message length

### General Chat Stats
- **Pererecos no Chat** - Active users in the last 5 minutes
- **Chat activity graph** (last 24 hours) with square root scaling
- **Average hourly activity** (all-time)
- **Top 10 emotes** used in chat

### Additional Features
- Real-time auto-refresh (5 second intervals)
- User search with autocomplete
- 7TV emote rendering in messages
- Timezone-aware graphs (converts UTC to local time)
- Responsive design

## Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **Motor** - Async MongoDB driver
- **TwitchIO** - Twitch chat bot library
- **Pydantic** - Data validation

### Frontend
- **Vanilla JavaScript** - No framework dependencies
- **CSS Grid/Flexbox** - Responsive layout
- **7TV API** - Emote rendering

### Database
- **MongoDB** - Document storage for chat messages

## Security Features

- Rate limiting with SlowAPI
- Input sanitization with bleach
- CORS configuration
- Security headers (X-Frame-Options, CSP, etc.)
- MongoDB query timeouts and limits
- Request size limits
- Twitch username validation

## Installation

### Prerequisites
- Python 3.11+
- MongoDB
- Twitch OAuth token

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings
```

### Environment Variables

```env
# Required
TWITCH_OAUTH_TOKEN=oauth:your_token_here
TWITCH_CHANNEL=your_channel

# Optional
TWITCH_CLIENT_ID=your_client_id
TWITCH_CLIENT_SECRET=your_client_secret
TWITCH_REFRESH_TOKEN=your_refresh_token

MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=twitch_stats

SEVENTV_EMOTE_SET_ID=your_7tv_emote_set_id
CORS_ORIGINS=*
```

### Running

```bash
# Start the backend (includes bot and API)
cd backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Access the dashboard at `http://localhost:8000`

### Production Deployment

Use the included `nginx.conf` as a reference for reverse proxy setup:

```bash
# Copy nginx config
sudo cp nginx.conf /etc/nginx/sites-available/pererecos-stats
sudo ln -s /etc/nginx/sites-available/pererecos-stats /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## API Endpoints

| Endpoint | Description | Rate Limit |
|----------|-------------|------------|
| `GET /api/v1/health` | Health check | 120/min |
| `GET /api/v1/stats/user/{username}` | User statistics | 30/min |
| `GET /api/v1/stats/leaderboard` | Top chatters | 60/min |
| `GET /api/v1/stats/rising-stars` | Growth leaders | 30/min |
| `GET /api/v1/stats/hour-leaders` | Hourly leaders | 30/min |
| `GET /api/v1/stats/top-writers` | Longest messages | 30/min |
| `GET /api/v1/stats/active-chatters` | Active users | 60/min |
| `GET /api/v1/stats/chat-activity` | Last 24h activity | 60/min |
| `GET /api/v1/stats/overall-activity` | All-time activity | 30/min |
| `GET /api/v1/stats/top-emotes` | Most used emotes | 30/min |
| `GET /api/v1/stats/search?q=` | User search | 60/min |
| `GET /api/v1/stats/compare/{user1}/{user2}` | Compare users | 20/min |

## License

MIT
