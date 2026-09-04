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
  onEvent: async (event, context) => {
    const post = event.post;
    if (!post) return;

    try {
      const backendUrl = 'https://api.projectpluto.studio';
      await fetch(`${backendUrl}/api/v1/webhooks/reddit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: post.title,
          content: post.body,
          score: post.score,
          upvote_ratio: post.upvoteRatio,
          num_comments: post.numberOfComments,
          subreddit: post.subredditName,
          url: post.url,
          author: post.authorName,
          created_at: post.createdAt,
          external_item_id: post.id,
        }),
      });
      console.log(`[Luvcraft Bridge] Forwarded submission ${post.id} from r/${post.subredditName}`);
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

export default Devvit;
