// ============================================================================
// FEEDBACK FORM VALIDATION & SUBMISSION
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('feedbackForm');
    const submitBtn = document.getElementById('submitBtn');
    const ratingError = document.getElementById('ratingError');
    
    if (form) {
        form.addEventListener('submit', function(e) {
            // Check if rating is selected
            const ratingSelected = form.querySelector('input[name="rating"]:checked');
            
            if (!ratingSelected) {
                e.preventDefault();
                ratingError.style.display = 'flex';
                ratingError.style.alignItems = 'center';
                ratingError.style.gap = '0.5rem';
                ratingError.style.color = 'var(--danger)';
                ratingError.style.marginTop = '0.5rem';
                
                // Scroll to rating section
                document.querySelector('.star-rating-input').scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });
                
                return false;
            }
            
            // Hide error if rating is selected
            ratingError.style.display = 'none';
            
            // Disable submit button to prevent double submission
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';
        });
        
        // Hide error when rating is selected
        const ratingInputs = form.querySelectorAll('input[name="rating"]');
        ratingInputs.forEach(input => {
            input.addEventListener('change', function() {
                ratingError.style.display = 'none';
            });
        });
    }
});
