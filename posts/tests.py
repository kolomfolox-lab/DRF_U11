from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from .models import Post
from .serializers import PostSerializer

class PostSerializerTestCase(TestCase):
    """
    Unit tests for PostSerializer validation logic.
    """
    def test_serializer_with_valid_data(self):
        data = {
            'title': 'Test Post Title',
            'content': 'This is a valid content with more than ten characters.'
        }
        serializer = PostSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_serializer_with_empty_title(self):
        data = {
            'title': '',
            'content': 'This is a valid content with more than ten characters.'
        }
        serializer = PostSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('title', serializer.errors)

    def test_serializer_with_short_content(self):
        data = {
            'title': 'Test Post Title',
            'content': 'Short'
        }
        serializer = PostSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('content', serializer.errors)


class PostAPIPermissionTestCase(TestCase):
    """
    Unit/API tests for Post creation and permissions.
    """
    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user(username='user1', password='password123')
        self.user2 = User.objects.create_user(username='user2', password='password123')
        
        # Create a post owned by user1
        self.post1 = Post.objects.create(
            author=self.user1,
            title='User 1 Post',
            content='Content for User 1 Post (longer than 10 chars)'
        )

    def test_create_post_unauthenticated(self):
        url = reverse('post-list')
        response = self.client.post(url, {'title': 'New Post', 'content': 'Valid content length'})
        # Since authentication is required to create a post, unauthenticated request should fail
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_create_post_authenticated(self):
        self.client.force_authenticate(user=self.user1)
        url = reverse('post-list')
        data = {
            'title': 'Auth User Post',
            'content': 'Content for Auth User Post (longer than 10 chars)'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Auth User Post')
        
        # Verify the author is automatically set to the authenticated user
        post = Post.objects.get(id=response.data['id'])
        self.assertEqual(post.author, self.user1)

    def test_update_post_by_owner(self):
        self.client.force_authenticate(user=self.user1)
        url = reverse('post-detail', kwargs={'pk': self.post1.pk})
        data = {
            'title': 'Updated Title by Owner',
            'content': 'Updated content for User 1 Post (longer than 10 chars)'
        }
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Updated Title by Owner')

    def test_update_post_by_non_owner(self):
        self.client.force_authenticate(user=self.user2)
        url = reverse('post-detail', kwargs={'pk': self.post1.pk})
        data = {
            'title': 'Attempted Update by Non-owner',
            'content': 'Attempted update content (longer than 10 chars)'
        }
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PostIntegrationTestCase(TestCase):
    """
    Integration tests covering the complete user flow:
    Register -> Obtain Token -> Create Post with Token -> Retrieve Post -> Update Post with Token
    """
    def setUp(self):
        self.client = APIClient()
        self.username = 'integration_user'
        self.password = 'secure_password_123'

    def test_complete_integration_flow(self):
        # 1. Register a new user
        register_url = reverse('register')
        register_data = {
            'username': self.username,
            'password': self.password,
            'confirm_password': self.password
        }
        register_response = self.client.post(register_url, register_data)
        self.assertEqual(register_response.status_code, status.HTTP_200_OK)
        self.assertEqual(register_response.data['message'], 'User created')

        # Verify user actually created in database
        self.assertTrue(User.objects.filter(username=self.username).exists())
        user = User.objects.get(username=self.username)

        # 2. Login / Obtain Token
        # The default obtain_auth_token URL is api_token_auth
        token_url = reverse('api_token_auth')
        token_data = {
            'username': self.username,
            'password': self.password
        }
        token_response = self.client.post(token_url, token_data)
        self.assertEqual(token_response.status_code, status.HTTP_200_OK)
        self.assertIn('token', token_response.data)
        token_key = token_response.data['token']

        # 3. Create a post using the obtained Token
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token_key)
        post_url = reverse('post-list')
        post_data = {
            'title': 'Integration Post Title',
            'content': 'This is integration post content that is long enough.'
        }
        create_response = self.client.post(post_url, post_data)
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data['title'], 'Integration Post Title')
        post_id = create_response.data['id']

        # 4. Retrieve the post
        detail_url = reverse('post-detail', kwargs={'pk': post_id})
        # Try retrieving without token first (retrieve is public)
        self.client.credentials()  # clear credentials
        get_response = self.client.get(detail_url)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data['title'], 'Integration Post Title')

        # 5. Update the post with the Token
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token_key)
        update_data = {
            'title': 'Integration Post Updated Title',
            'content': 'This is integration post content that is long enough and updated.'
        }
        update_response = self.client.put(detail_url, update_data)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data['title'], 'Integration Post Updated Title')

        # Verify in database
        db_post = Post.objects.get(id=post_id)
        self.assertEqual(db_post.title, 'Integration Post Updated Title')
        self.assertEqual(db_post.author, user)


class QueryOptimizationTestCase(TestCase):
    """
    Unit tests for checking N+1 query optimization.
    """
    def setUp(self):
        self.user = User.objects.create_user(username='author_user', password='password123')
        # Create multiple posts
        for i in range(5):
            Post.objects.create(
                author=self.user,
                title=f'Post {i}',
                content=f'Content for post {i} (10+ characters)'
            )

    def test_n_plus_one_optimization(self):
        # Using select_related, accessing author on all posts should take exactly 1 query.
        with self.assertNumQueries(1):
            posts = list(Post.objects.select_related('author').all())
            for post in posts:
                # Accessing author shouldn't trigger additional queries because of select_related
                author_username = post.author.username
                self.assertEqual(author_username, 'author_user')

