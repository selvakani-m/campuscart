from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.db import transaction
from django.contrib.auth.models import User
from django.contrib.auth.forms import PasswordChangeForm
from django.core.cache import cache
from django.http import JsonResponse, HttpResponse
import random
import string
from .models import Product, Category, ProductRequest, UserProfile
from .forms import UserRegistrationForm, ProductForm, ProductRequestForm

# ==================== MAIN PAGES ====================

def index(request):
    """Homepage with latest products and categories"""
    products = Product.objects.filter(is_sold=False).order_by('-created_at')[:12]
    categories = Category.objects.all()
    return render(request, 'index.html', {
        'products': products,
        'categories': categories
    })

def register(request):
    """User registration page"""
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, '✅ Registration successful! Welcome to CampusKart.')
            return redirect('dashboard')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'register.html', {'form': form})

def user_login(request):
    """User login page"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f'✅ Welcome back, {user.username}!')
            return redirect('dashboard')
        else:
            messages.error(request, '❌ Invalid username or password. Please try again.')
    
    return render(request, 'login.html')

def user_logout(request):
    """User logout"""
    logout(request)
    messages.info(request, '👋 You have been logged out successfully.')
    return redirect('index')

@login_required
def dashboard(request):
    """User dashboard showing selling and buying activities"""
    # Get products the user is selling
    selling = Product.objects.filter(seller=request.user).order_by('-created_at')
    
    # Get requests the user has made (as buyer)
    buying = ProductRequest.objects.filter(buyer=request.user).order_by('-created_at')
    
    # Get requests received for user's products (as seller)
    received = ProductRequest.objects.filter(product__seller=request.user).order_by('-created_at')
    
    context = {
        'selling': selling,
        'buying': buying,
        'received': received,
        'selling_count': selling.count(),
        'buying_count': buying.count(),
        'received_count': received.count(),
        'sold_count': selling.filter(is_sold=True).count(),
    }
    return render(request, 'dashboard.html', context)

# ==================== PRODUCT RELATED ====================

@login_required
def product_list(request):
    """List all available products with filters"""
    products = Product.objects.filter(is_sold=False)
    
    # Search
    query = request.GET.get('q')
    if query:
        products = products.filter(
            Q(name__icontains=query) | 
            Q(description__icontains=query)
        )
    
    # Category filter
    category_id = request.GET.get('category')
    if category_id:
        products = products.filter(category_id=category_id)
    
    # Condition filter
    condition = request.GET.get('condition')
    if condition:
        products = products.filter(condition=condition)
    
    return render(request, 'product_list.html', {
        'products': products,
        'categories': Category.objects.all()
    })

@login_required
def product_detail(request, product_id):
    """View single product details"""
    product = get_object_or_404(Product, id=product_id)
    
    # Check if user has already requested this product
    has_requested = ProductRequest.objects.filter(
        product=product, 
        buyer=request.user
    ).exists()
    
    return render(request, 'product_detail.html', {
        'product': product,
        'has_requested': has_requested,
        'is_owner': request.user == product.seller
    })

@login_required
def buy_product(request, product_id):
    """Direct purchase - marks product as sold immediately"""
    product = get_object_or_404(Product, id=product_id)
    
    # Check if user is trying to buy their own product
    if request.user == product.seller:
        messages.error(request, '❌ You cannot buy your own product!')
        return redirect('product_detail', product_id=product.id)
    
    # Check if product is already sold
    if product.is_sold:
        messages.error(request, '❌ This product has already been sold!')
        return redirect('product_detail', product_id=product.id)
    
    if request.method == 'POST':
        # Create a completed request record
        message = request.POST.get('message', '')
        
        ProductRequest.objects.create(
            product=product,
            buyer=request.user,
            message=message,
            status='completed'
        )
        
        # Mark product as sold
        product.is_sold = True
        product.save()
        
        messages.success(request, f'✅ Congratulations! You have successfully purchased {product.name}. Please contact the seller to arrange pickup.')
        return redirect('dashboard')
    
    return redirect('product_detail', product_id=product.id)

@login_required
def request_product(request, product_id):
    """Request to buy - seller needs to approve"""
    product = get_object_or_404(Product, id=product_id)
    
    # Check if user is trying to request their own product
    if request.user == product.seller:
        messages.error(request, '❌ You cannot request your own product!')
        return redirect('product_detail', product_id=product.id)
    
    # Check if product is already sold
    if product.is_sold:
        messages.error(request, '❌ This product has already been sold!')
        return redirect('product_detail', product_id=product.id)
    
    # Check if already requested
    existing_request = ProductRequest.objects.filter(
        product=product,
        buyer=request.user
    ).first()
    
    if existing_request:
        if existing_request.status == 'pending':
            messages.warning(request, '⏳ You have already requested this product. Please wait for seller response.')
        elif existing_request.status == 'accepted':
            messages.info(request, '✅ Your request has been accepted! Please contact the seller to complete the transaction.')
        elif existing_request.status == 'rejected':
            messages.error(request, '❌ Your previous request was rejected. You can try again.')
        return redirect('product_detail', product_id=product.id)
    
    if request.method == 'POST':
        message = request.POST.get('message', '')
        
        ProductRequest.objects.create(
            product=product,
            buyer=request.user,
            message=message,
            status='pending'
        )
        
        messages.success(request, '✅ Request sent successfully! The seller will respond soon.')
        return redirect('product_detail', product_id=product.id)
    
    return redirect('product_detail', product_id=product.id)

# ==================== PRODUCT MANAGEMENT ====================

@login_required
def add_product(request):
    """Add a new product for sale"""
    categories = Category.objects.all()
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.seller = request.user
            product.save()
            messages.success(request, '✅ Product listed successfully!')
            return redirect('my_products')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = ProductForm()
    
    return render(request, 'add_product.html', {
        'form': form,
        'categories': categories
    })

@login_required
def my_products(request):
    """View all products listed by the user"""
    products = Product.objects.filter(seller=request.user).order_by('-created_at')
    return render(request, 'my_products.html', {'products': products})

@login_required
def edit_product(request, product_id):
    """Edit an existing product"""
    product = get_object_or_404(Product, id=product_id, seller=request.user)
    categories = Category.objects.all()
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ Product updated successfully!')
            return redirect('my_products')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = ProductForm(instance=product)
    
    return render(request, 'edit_product.html', {
        'form': form,
        'product': product,
        'categories': categories
    })

@login_required
def delete_product(request, product_id):
    """Delete a product"""
    product = get_object_or_404(Product, id=product_id, seller=request.user)
    
    if request.method == 'POST':
        product.delete()
        messages.success(request, '✅ Product deleted successfully!')
        return redirect('my_products')
    
    return render(request, 'delete_product.html', {'product': product})

# ==================== REQUESTS MANAGEMENT ====================

@login_required
def manage_requests(request):
    """Manage all requests (received and made)"""
    # Requests received for user's products (as seller)
    received = ProductRequest.objects.filter(
        product__seller=request.user
    ).order_by('-created_at')
    
    # Requests made by user (as buyer)
    made = ProductRequest.objects.filter(
        buyer=request.user
    ).order_by('-created_at')
    
    # Handle request status updates
    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')
        product_request = get_object_or_404(ProductRequest, id=request_id, product__seller=request.user)
        
        if action == 'accept':
            product_request.status = 'accepted'
            messages.success(request, '✅ Request accepted! The buyer will be notified.')
        elif action == 'reject':
            product_request.status = 'rejected'
            messages.success(request, '✅ Request rejected.')
        elif action == 'complete':
            product_request.status = 'completed'
            product_request.product.is_sold = True
            product_request.product.save()
            messages.success(request, '✅ Transaction completed! Product marked as sold.')
        
        product_request.save()
        return redirect('manage_requests')
    
    return render(request, 'requests.html', {
        'received': received,
        'made': made
    })

# ==================== PROFILE MANAGEMENT ====================

@login_required
def profile(request):
    """View and edit user profile"""
    user_profile = request.user.profile
    
    if request.method == 'POST':
        # Get form data
        phone_number = request.POST.get('phone_number', '')
        department = request.POST.get('department', '')
        current_year = request.POST.get('current_year', '')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        
        # Validate required fields
        if not department or not current_year:
            messages.error(request, '❌ Department and Current Year are required fields.')
            return render(request, 'profile.html', {'profile': user_profile})
        
        # Update user profile
        user_profile.phone_number = phone_number
        user_profile.department = department
        user_profile.current_year = current_year
        user_profile.save()
        
        # Update user info
        user = request.user
        user.first_name = first_name
        user.last_name = last_name
        user.save()
        
        messages.success(request, '✅ Profile updated successfully!')
        return redirect('profile')
    
    return render(request, 'profile.html', {'profile': user_profile})

@login_required
def delete_account(request):
    """Permanently delete user account"""
    if request.method == 'POST':
        user = request.user
        username = user.username
        
        # Get confirmation from form
        confirm_username = request.POST.get('confirm_username', '')
        
        # Verify username matches
        if confirm_username != username:
            messages.error(request, '❌ Username does not match. Account not deleted.')
            return redirect('profile')
        
        # Logout the user first
        logout(request)
        
        # Delete the user account (this will cascade delete profile and related data)
        try:
            with transaction.atomic():
                # Delete the user (cascade will delete profile, products, requests)
                user.delete()
                messages.success(request, f'✅ Account "{username}" has been permanently deleted. We\'re sorry to see you go!')
        except Exception as e:
            messages.error(request, f'❌ Error deleting account: {str(e)}')
            return redirect('profile')
        
        return redirect('index')
    
    return redirect('profile')

# ==================== PASSWORD CHANGE WITH OTP ====================

from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash

@login_required
def change_password(request):
    """Simple password change view"""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Important: keeps the user logged in
            update_session_auth_hash(request, user)
            messages.success(request, '✅ Your password was successfully updated!')
            return redirect('profile')
        else:
            for error in form.errors.values():
                messages.error(request, error)
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'change_password.html', {'form': form})
@login_required
def send_otp(request):
    """Send OTP to user's mobile"""
    print("=== SEND OTP CALLED ===")
    if request.method == 'POST':
        otp = ''.join(random.choices(string.digits, k=6))
        cache.set(f'otp_{request.user.id}', otp, timeout=300)
        print(f"📱 OTP for {request.user.username}: {otp}")
        return JsonResponse({'success': True, 'message': 'OTP sent', 'otp': otp})
    return JsonResponse({'success': False, 'message': 'Invalid request'})

@login_required
def verify_otp(request):
    """Verify OTP"""
    print("=== VERIFY OTP CALLED ===")
    if request.method == 'POST':
        entered_otp = request.POST.get('otp')
        stored_otp = cache.get(f'otp_{request.user.id}')
        if stored_otp and stored_otp == entered_otp:
            cache.delete(f'otp_{request.user.id}')
            return JsonResponse({'success': True, 'message': 'OTP verified'})
        return JsonResponse({'success': False, 'message': 'Invalid OTP'})
    return JsonResponse({'success': False, 'message': 'Invalid request'})

@login_required
def reset_password(request):
    """Reset password"""
    print("=== RESET PASSWORD CALLED ===")
    if request.method == 'POST':
        new_pass = request.POST.get('new_password')
        confirm_pass = request.POST.get('confirm_password')
        
        if new_pass != confirm_pass:
            return JsonResponse({'success': False, 'message': 'Passwords do not match'})
        
        if len(new_pass) < 8:
            return JsonResponse({'success': False, 'message': 'Password too short'})
        
        request.user.set_password(new_pass)
        request.user.save()
        update_session_auth_hash(request, request.user)
        
        return JsonResponse({'success': True, 'message': 'Password updated'})
    return JsonResponse({'success': False, 'message': 'Invalid request'})

# ==================== DEBUG ====================

def debug_urls(request):
    """Debug view to show all URLs"""
    from django.urls import get_resolver
    urls = []
    for pattern in get_resolver().url_patterns:
        urls.append(str(pattern.pattern))
    return HttpResponse('<br>'.join(urls))