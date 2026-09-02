# Telegram Media Bot

A private, user-initiated Telegram bot for retrieving media from links submitted directly by the user.

The project is designed as a personal media utility. The bot receives a URL through Telegram, determines the source platform and media type, retrieves the requested media, and returns it to the requesting user through Telegram.

## Current Features

The bot currently supports user-submitted links from several media platforms, including:

- YouTube
- Instagram
- TikTok
- X / Twitter
- Facebook
- Reddit integration is currently being developed

Depending on the platform and post type, the bot can handle:

- Video posts
- Single-image posts
- Multi-image galleries
- Telegram media albums

The bot only processes URLs explicitly submitted by the user. It does not automatically crawl websites or discover content.

## Reddit Integration

Reddit support is being developed using Reddit's approved API access.

The intended Reddit workflow is:

1. A user manually sends the Telegram bot the URL of a specific Reddit post.
2. The application identifies that individual Reddit post.
3. The application requests only the metadata necessary to identify the public media attached to that post.
4. For an image post or gallery, the application retrieves the URLs of the attached public images.
5. For supported Reddit-hosted video posts, the application may retrieve the media information necessary to obtain the requested video.
6. The requested media is returned to the same user through Telegram.

For example, if a user submits the URL of a Reddit post containing a five-image gallery, the application would retrieve metadata for that specific post, identify the five attached images, download them, and return them to the user as a Telegram media album.

## Reddit Data Usage

The application is not intended to:

- Crawl or scrape subreddits
- Automatically discover Reddit posts
- Monitor Reddit users or communities
- Collect comments
- Collect voting data
- Collect user profiles
- Access private Reddit information
- Vote on posts or comments
- Submit posts or comments
- Send Reddit messages
- Perform moderation actions
- Perform bulk Reddit data collection

Reddit requests are initiated individually when the user supplies a specific Reddit post URL.

The application operates externally through Telegram and does not provide an embedded Reddit or subreddit experience.

## Architecture

The project currently uses a combination of:

- Python
- python-telegram-bot
- yt-dlp
- gallery-dl
- Playwright

Different retrieval methods are selected depending on the platform and media type.

Reddit integration is intended to use Reddit's authorized API access rather than attempting to circumvent Reddit access restrictions.

## Privacy and Credentials

Private credentials are not stored in this repository.

The following types of local data are excluded from version control:

- Telegram bot tokens
- API credentials and secrets
- Authentication cookies
- Browser profiles
- Downloaded media
- Temporary files
- Local configuration files

Sensitive configuration is stored separately from the public source code.

## Project Status

This is an actively developed personal project.

Current work is focused on adding Reddit support through an authorized API workflow while preserving the existing media retrieval functionality for other supported platforms.