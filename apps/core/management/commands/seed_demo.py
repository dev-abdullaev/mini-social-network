import random

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.posts.models import Comment, Like, Post
from apps.users.models import Follow, User

# Demo accounts share this email domain so `--flush` can find and remove them
# without touching real users.
DEMO_DOMAIN = "demo.local"
DEMO_PASSWORD = "demopass123"

USERS = [
    ("michael", "Michael Scott"),
    ("kamran", "Kamran Aliyev"),
    ("alice", "Alice Johnson"),
    ("bob", "Bob Smith"),
    ("diana", "Diana Prince"),
]

POSTS = [
    ("Hello world", "i love rust and clean architecture"),
    ("Tashkent", "tashkent is the capital of uzbekistan"),
    ("London", "london is the capital of Great Britain"),
    ("On testing", "tests are the documentation that never lies"),
    ("Coffee", "the third cup is always the best one"),
    ("Django tips", "select_related and prefetch_related save your database"),
    ("Weekend", "hiking beats scrolling every single time"),
    ("Music", "lo-fi beats while coding is underrated"),
    ("Books", "reading one chapter a day compounds fast"),
    ("Cooking", "pasta is easy until you try to time it right"),
]

COMMENTS = [
    "Great post!",
    "Totally agree with this.",
    "Thanks for sharing.",
    "This made my day.",
    "Interesting take.",
    "Never thought about it this way.",
    "Well written.",
    "I learned something new.",
]


class Command(BaseCommand):
    help = "Seed the database with demo users, posts, comments, likes, and follows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing demo data (users under @demo.local) before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["flush"]:
            deleted, _ = User.objects.filter(email__endswith=f"@{DEMO_DOMAIN}").delete()
            self.stdout.write(f"Flushed {deleted} demo row(s).")

        # Deterministic run so repeated seeds are comparable.
        rng = random.Random(42)

        users = []
        for username, full_name in USERS:
            email = f"{username}@{DEMO_DOMAIN}"
            user, created = User.objects.get_or_create(
                email=email,
                defaults={"username": username, "full_name": full_name, "is_verified": True},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])
            users.append(user)

        # 2 posts per user, drawn from the pool.
        posts = []
        for i, user in enumerate(users):
            for title, content in POSTS[i * 2 : i * 2 + 2]:
                post = Post.objects.create(author=user, title=title, content=content)
                posts.append(post)

        # Comments: each post gets 0-3 comments from random non-author users.
        for post in posts:
            others = [u for u in users if u.id != post.author_id]
            for author in rng.sample(others, k=rng.randint(0, min(3, len(others)))):
                Comment.objects.create(post=post, author=author, content=rng.choice(COMMENTS))

        # Likes: each user likes a random subset of posts they didn't write.
        for user in users:
            likeable = [p for p in posts if p.author_id != user.id]
            for post in rng.sample(likeable, k=rng.randint(0, len(likeable) // 2)):
                Like.objects.get_or_create(user=user, post=post)

        # Follows: each user follows 1-3 random others.
        for user in users:
            others = [u for u in users if u.id != user.id]
            for target in rng.sample(others, k=rng.randint(1, min(3, len(others)))):
                Follow.objects.get_or_create(follower=user, following=target)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(users)} users, {len(posts)} posts, "
                f"{Comment.objects.count()} comments, {Like.objects.count()} likes, "
                f"{Follow.objects.count()} follows. Password for all: {DEMO_PASSWORD}"
            )
        )
