
"""Conversational promotional notification messages for Pairza."""

from typing import TypedDict


class EngagementMessage(TypedDict):
    id: str
    category: str
    body: str
    url: str


ENGAGEMENT_MESSAGES: tuple[EngagementMessage, ...] = (
    # Boredom
    {
        "id": "boredom_001",
        "category": "boredom",
        "body": "Got a few minutes? There's a mystery waiting to challenge your brain.",
        "url": "/home",
    },
    {
        "id": "boredom_002",
        "category": "boredom",
        "body": "Bored of scrolling? Try solving something instead.",
        "url": "/home",
    },
    {
        "id": "boredom_003",
        "category": "boredom",
        "body": "Your next little brain break could be surprisingly interesting.",
        "url": "/home",
    },
    {
        "id": "boredom_004",
        "category": "boredom",
        "body": "A few minutes, a curious clue, and a fresh challenge. Sounds good?",
        "url": "/home",
    },
    {
        "id": "boredom_005",
        "category": "boredom",
        "body": "Need a break from the usual routine? Solve something unusual.",
        "url": "/home",
    },
    {
        "id": "boredom_006",
        "category": "boredom",
        "body": "Your brain called. It wants something more interesting to do.",
        "url": "/home",
    },
    {
        "id": "boredom_007",
        "category": "boredom",
        "body": "Turn those spare minutes into a little detective work.",
        "url": "/home",
    },
    {
        "id": "boredom_008",
        "category": "boredom",
        "body": "Nothing exciting happening? Maybe it's time to find a mystery.",
        "url": "/home",
    },
    {
        "id": "boredom_009",
        "category": "boredom",
        "body": "A different kind of break is just one mystery away.",
        "url": "/home",
    },
    {
        "id": "boredom_010",
        "category": "boredom",
        "body": "Ready to swap another scroll for a clever challenge?",
        "url": "/home",
    },
    {
        "id": "boredom_011",
        "category": "boredom",
        "body": "There's always room for one more interesting question.",
        "url": "/home",
    },
    {
        "id": "boredom_012",
        "category": "boredom",
        "body": "Take a tiny break. Give your curiosity something to do.",
        "url": "/home",
    },
    {
        "id": "boredom_013",
        "category": "boredom",
        "body": "Looking for something different? Try thinking like a detective.",
        "url": "/home",
    },
    {
        "id": "boredom_014",
        "category": "boredom",
        "body": "A quiet moment is the perfect time for a tricky mystery.",
        "url": "/home",
    },
    {
        "id": "boredom_015",
        "category": "boredom",
        "body": "Give your usual break a plot twist.",
        "url": "/home",
    },

    # Funny / Sarcastic
    {
        "id": "funny_001",
        "category": "funny",
        "body": "Your detective badge is getting dusty. Just saying.",
        "url": "/home",
    },
    {
        "id": "funny_002",
        "category": "funny",
        "body": "No pressure, but that mystery isn't going to solve itself.",
        "url": "/home",
    },
    {
        "id": "funny_003",
        "category": "funny",
        "body": "Brain cells: assembled. Mystery: pending.",
        "url": "/home",
    },
    {
        "id": "funny_004",
        "category": "funny",
        "body": "You look like someone who could use a suspiciously good puzzle.",
        "url": "/home",
    },
    {
        "id": "funny_005",
        "category": "funny",
        "body": "Scrolling again? Your detective instincts deserve better.",
        "url": "/home",
    },
    {
        "id": "funny_006",
        "category": "funny",
        "body": "Warning: may cause excessive thinking and dramatic deductions.",
        "url": "/home",
    },
    {
        "id": "funny_007",
        "category": "funny",
        "body": "A mystery has entered the chat. Your move.",
        "url": "/home",
    },
    {
        "id": "funny_008",
        "category": "funny",
        "body": "Sherlock had a partner too. Just putting that out there.",
        "url": "/home",
    },
    {
        "id": "funny_009",
        "category": "funny",
        "body": "Your brain is not a decorative accessory. Put it to work.",
        "url": "/home",
    },
    {
        "id": "funny_010",
        "category": "funny",
        "body": "Today's plan: investigate first, celebrate the correct answer later.",
        "url": "/home",
    },
    {
        "id": "funny_011",
        "category": "funny",
        "body": "Plot twist: the clue you ignored might be the important one.",
        "url": "/home",
    },
    {
        "id": "funny_012",
        "category": "funny",
        "body": "Your inner detective has been waiting long enough.",
        "url": "/home",
    },
    {
        "id": "funny_013",
        "category": "funny",
        "body": "Side effects include saying 'wait, that doesn't make sense!'",
        "url": "/home",
    },
    {
        "id": "funny_014",
        "category": "funny",
        "body": "The clues are innocent until proven suspicious.",
        "url": "/home",
    },
    {
        "id": "funny_015",
        "category": "funny",
        "body": "Go on. Show that mystery who's boss.",
        "url": "/home",
    },

    # Curiosity
    {
        "id": "curiosity_001",
        "category": "curiosity",
        "body": "What if the smallest clue changes the entire story?",
        "url": "/home",
    },
    {
        "id": "curiosity_002",
        "category": "curiosity",
        "body": "Would you trust a witness who sounds completely certain?",
        "url": "/home",
    },
    {
        "id": "curiosity_003",
        "category": "curiosity",
        "body": "Sometimes two different perspectives reveal one answer.",
        "url": "/home",
    },
    {
        "id": "curiosity_004",
        "category": "curiosity",
        "body": "Can you spot what everyone else might miss?",
        "url": "/home",
    },
    {
        "id": "curiosity_005",
        "category": "curiosity",
        "body": "What would you investigate first if the clues didn't agree?",
        "url": "/home",
    },
    {
        "id": "curiosity_006",
        "category": "curiosity",
        "body": "One detail can change everything. Would you notice it?",
        "url": "/home",
    },
    {
        "id": "curiosity_007",
        "category": "curiosity",
        "body": "How well do you understand someone else's point of view?",
        "url": "/home",
    },
    {
        "id": "curiosity_008",
        "category": "curiosity",
        "body": "What happens when two people know different parts of the truth?",
        "url": "/home",
    },
    {
        "id": "curiosity_009",
        "category": "curiosity",
        "body": "Could you solve a mystery without seeing every clue?",
        "url": "/home",
    },
    {
        "id": "curiosity_010",
        "category": "curiosity",
        "body": "There's more than one way to look at a mystery.",
        "url": "/home",
    },
    {
        "id": "curiosity_011",
        "category": "curiosity",
        "body": "Would you notice a contradiction hiding in plain sight?",
        "url": "/home",
    },
    {
        "id": "curiosity_012",
        "category": "curiosity",
        "body": "What if the answer is simpler than the clues make it seem?",
        "url": "/home",
    },
    {
        "id": "curiosity_013",
        "category": "curiosity",
        "body": "Can two incomplete stories make one complete picture?",
        "url": "/home",
    },
    {
        "id": "curiosity_014",
        "category": "curiosity",
        "body": "Which detail would you question first?",
        "url": "/home",
    },
    {
        "id": "curiosity_015",
        "category": "curiosity",
        "body": "Some questions are much more interesting when shared.",
        "url": "/home",
    },

    # Challenge
    {
        "id": "challenge_001",
        "category": "challenge",
        "body": "Think you have sharp instincts? Put them to the test.",
        "url": "/home",
    },
    {
        "id": "challenge_002",
        "category": "challenge",
        "body": "Ready for a challenge that rewards careful thinking?",
        "url": "/home",
    },
    {
        "id": "challenge_003",
        "category": "challenge",
        "body": "Don't guess too quickly. Every detail matters.",
        "url": "/home",
    },
    {
        "id": "challenge_004",
        "category": "challenge",
        "body": "Can you connect the clues before the pieces fall into place?",
        "url": "/home",
    },
    {
        "id": "challenge_005",
        "category": "challenge",
        "body": "Your next reasoning challenge is waiting.",
        "url": "/home",
    },
    {
        "id": "challenge_006",
        "category": "challenge",
        "body": "Look closer. Think deeper. Trust the evidence.",
        "url": "/home",
    },
    {
        "id": "challenge_007",
        "category": "challenge",
        "body": "A clever answer starts with a better question.",
        "url": "/home",
    },
    {
        "id": "challenge_008",
        "category": "challenge",
        "body": "Can you separate facts from assumptions?",
        "url": "/home",
    },
    {
        "id": "challenge_009",
        "category": "challenge",
        "body": "Not every obvious answer is the right one.",
        "url": "/home",
    },
    {
        "id": "challenge_010",
        "category": "challenge",
        "body": "Put your deduction skills to work on something unusual.",
        "url": "/home",
    },
    {
        "id": "challenge_011",
        "category": "challenge",
        "body": "The real challenge is noticing what doesn't fit.",
        "url": "/home",
    },
    {
        "id": "challenge_012",
        "category": "challenge",
        "body": "Can you make sense of clues that seem to disagree?",
        "url": "/home",
    },
    {
        "id": "challenge_013",
        "category": "challenge",
        "body": "Take your time. A sharp mind doesn't need to rush.",
        "url": "/home",
    },
    {
        "id": "challenge_014",
        "category": "challenge",
        "body": "Ready to test how far your logic can take you?",
        "url": "/home",
    },
    {
        "id": "challenge_015",
        "category": "challenge",
        "body": "One mystery. Several clues. Can you find the connection?",
        "url": "/home",
    },

    # Social
    {
        "id": "social_001",
        "category": "social",
        "body": "Some mysteries are better solved with another perspective.",
        "url": "/home",
    },
    {
        "id": "social_002",
        "category": "social",
        "body": "Ever wondered how a stranger approaches the same problem?",
        "url": "/home",
    },
    {
        "id": "social_003",
        "category": "social",
        "body": "Two minds can notice what one might miss.",
        "url": "/home",
    },
    {
        "id": "social_004",
        "category": "social",
        "body": "A new mystery could introduce you to a new way of thinking.",
        "url": "/home",
    },
    {
        "id": "social_005",
        "category": "social",
        "body": "You bring one perspective. Someone else brings another.",
        "url": "/home",
    },
    {
        "id": "social_006",
        "category": "social",
        "body": "Ready to put teamwork and deduction together?",
        "url": "/home",
    },
    {
        "id": "social_007",
        "category": "social",
        "body": "The best clue might be the one someone else noticed.",
        "url": "/home",
    },
    {
        "id": "social_008",
        "category": "social",
        "body": "A little teamwork can make a big difference.",
        "url": "/home",
    },
    {
        "id": "social_009",
        "category": "social",
        "body": "See how two different minds approach one mystery.",
        "url": "/home",
    },
    {
        "id": "social_010",
        "category": "social",
        "body": "A stranger's observation might change your whole theory.",
        "url": "/home",
    },
    {
        "id": "social_011",
        "category": "social",
        "body": "Good conversations can start with curious questions.",
        "url": "/home",
    },
    {
        "id": "social_012",
        "category": "social",
        "body": "Think together. Compare clues. Find the answer.",
        "url": "/home",
    },
    {
        "id": "social_013",
        "category": "social",
        "body": "Your next teammate might think very differently from you.",
        "url": "/home",
    },
    {
        "id": "social_014",
        "category": "social",
        "body": "One mystery is easier to understand from two sides.",
        "url": "/home",
    },
    {
        "id": "social_015",
        "category": "social",
        "body": "Curiosity is even better when you can share it.",
        "url": "/home",
    },

    # Suspense
    {
        "id": "suspense_001",
        "category": "suspense",
        "body": "Something about this story doesn't quite add up.",
        "url": "/home",
    },
    {
        "id": "suspense_002",
        "category": "suspense",
        "body": "The details seem clear. The truth might not be.",
        "url": "/home",
    },
    {
        "id": "suspense_003",
        "category": "suspense",
        "body": "There's a missing piece somewhere. Can you find it?",
        "url": "/home",
    },
    {
        "id": "suspense_004",
        "category": "suspense",
        "body": "Two accounts. One mystery. Something doesn't match.",
        "url": "/home",
    },
    {
        "id": "suspense_005",
        "category": "suspense",
        "body": "The first explanation isn't always the final answer.",
        "url": "/home",
    },
    {
        "id": "suspense_006",
        "category": "suspense",
        "body": "A quiet detail may be hiding a bigger story.",
        "url": "/home",
    },
    {
        "id": "suspense_007",
        "category": "suspense",
        "body": "Everything looks connected. But is it really?",
        "url": "/home",
    },
    {
        "id": "suspense_008",
        "category": "suspense",
        "body": "One unanswered question can change the whole investigation.",
        "url": "/home",
    },
    {
        "id": "suspense_009",
        "category": "suspense",
        "body": "The clues are there. The connection is yours to discover.",
        "url": "/home",
    },
    {
        "id": "suspense_010",
        "category": "suspense",
        "body": "Something is missing from this picture.",
        "url": "/home",
    },
    {
        "id": "suspense_011",
        "category": "suspense",
        "body": "What happened is one question. Why it happened is another.",
        "url": "/home",
    },
    {
        "id": "suspense_012",
        "category": "suspense",
        "body": "A detail nobody questioned could hold the answer.",
        "url": "/home",
    },
    {
        "id": "suspense_013",
        "category": "suspense",
        "body": "The story has two sides. Have you heard them both?",
        "url": "/home",
    },
    {
        "id": "suspense_014",
        "category": "suspense",
        "body": "The evidence tells a story. Are you reading it correctly?",
        "url": "/home",
    },
    {
        "id": "suspense_015",
        "category": "suspense",
        "body": "Not everything is as straightforward as it first appears.",
        "url": "/home",
    },

    # Random
    {
        "id": "random_001",
        "category": "random",
        "body": "A curious mind always finds something worth exploring.",
        "url": "/home",
    },
    {
        "id": "random_002",
        "category": "random",
        "body": "Today feels like a good day to question the obvious.",
        "url": "/home",
    },
    {
        "id": "random_003",
        "category": "random",
        "body": "Trust your curiosity. It might lead somewhere interesting.",
        "url": "/home",
    },
    {
        "id": "random_004",
        "category": "random",
        "body": "A new perspective can make an ordinary day interesting.",
        "url": "/home",
    },
    {
        "id": "random_005",
        "category": "random",
        "body": "What would your first theory be?",
        "url": "/home",
    },
    {
        "id": "random_006",
        "category": "random",
        "body": "Keep asking questions. That's where interesting things begin.",
        "url": "/home",
    },
    {
        "id": "random_007",
        "category": "random",
        "body": "A little curiosity can take you a long way.",
        "url": "/home",
    },
    {
        "id": "random_008",
        "category": "random",
        "body": "Try looking at the same problem from a different angle.",
        "url": "/home",
    },
    {
        "id": "random_009",
        "category": "random",
        "body": "Your next interesting discovery could start with one clue.",
        "url": "/home",
    },
    {
        "id": "random_010",
        "category": "random",
        "body": "Make room for a little unexpected thinking today.",
        "url": "/home",
    },
    {
        "id": "random_011",
        "category": "random",
        "body": "The fun often begins before you know the answer.",
        "url": "/home",
    },
    {
        "id": "random_012",
        "category": "random",
        "body": "A good question can be more interesting than a quick answer.",
        "url": "/home",
    },
    {
        "id": "random_013",
        "category": "random",
        "body": "Take a moment to follow an interesting thought.",
        "url": "/home",
    },
    {
        "id": "random_014",
        "category": "random",
        "body": "There's always another way to connect the dots.",
        "url": "/home",
    },
    {
        "id": "random_015",
        "category": "random",
        "body": "A fresh challenge might be exactly what you need today.",
        "url": "/home",
    },
)
