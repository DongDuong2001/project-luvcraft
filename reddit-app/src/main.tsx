import { Devvit } from '@devvit/public-api';

Devvit.configure({
  http: true,
  redditAPI: true,
});

/**
 * Event Trigger: Forward new community discussion submissions to Project Luvcraft backend.
 */
Devvit.addTrigger({
  event: 'PostSubmit',
  onEvent: async (event, _context) => {
    const post = event.post as Record<string, any> | undefined;
    if (!post) return;

    try {
      const backendUrl = 'https://api.projectpluto.studio';
      const title = String(post.title || '');
      const content = String(post.text || post.selftext || post.body || '');
      const score = Number(post.score || 0);
      const upvoteRatio = typeof post.upvoteRatio === 'number' ? post.upvoteRatio : undefined;
      const numComments = Number(post.numComments || post.numberOfComments || 0);
      const subreddit = String(post.subredditName || event.subreddit?.name || 'unknown');
      const url = String(post.url || post.permalink || '');
      const author = String(post.authorName || post.author || '');
      const createdAt = post.createdAt ? new Date(post.createdAt).toISOString() : undefined;
      const externalItemId = String(post.id || '');

      await fetch(`${backendUrl}/api/v1/webhooks/reddit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          content,
          score,
          upvote_ratio: upvoteRatio,
          num_comments: numComments,
          subreddit,
          url,
          author,
          created_at: createdAt,
          external_item_id: externalItemId,
        }),
      });
      console.log(`[Luvcraft Bridge] Forwarded submission ${externalItemId} from r/${subreddit}`);
    } catch (err) {
      console.error('[Luvcraft Bridge] Failed to forward submission:', err);
    }
  },
});

/**
 * Custom Interactive Post Widget: Fandom Pulse & Community Vibe Check
 */
Devvit.addCustomPostType({
  name: 'Project Luvcraft Fandom Pulse',
  render: (_context) => {
    return (
      <vstack gap="medium" padding="medium" cornerRadius="medium" backgroundColor="#0b1120">
        <text size="large" weight="bold" color="#60a5fa">
          Project Luvcraft · Fandom Pulse
        </text>
        <text size="small" color="#94a3b8">
          Real-time community sentiment and demand signals analyzed by Project Pluto AI.
        </text>
        <hstack gap="small">
          <text size="small" color="#38bdf8">Vibe: Positive (84%)</text>
          <text size="small" color="#a78bfa">· Topic: Gameplay & Soundtrack</text>
        </hstack>
      </vstack>
    );
  },
});

/**
 * Menu Item to quickly spawn the interactive widget post in the subreddit
 */
Devvit.addMenuItem({
  label: 'Create Project Luvcraft Pulse Post',
  location: 'subreddit',
  forUserType: 'moderator',
  onPress: async (_event, context) => {
    const { reddit, ui } = context;
    const currentSubreddit = await reddit.getCurrentSubreddit();
    await reddit.submitPost({
      title: 'Project Luvcraft: Live Fandom Pulse & Sentiment',
      subredditName: currentSubreddit.name,
      preview: (
        <vstack padding="medium">
          <text>Loading Project Luvcraft Live Pulse...</text>
        </vstack>
      ),
    });
    ui.showToast({ text: 'Project Luvcraft Pulse Post Created!' });
  },
});

export default Devvit;

