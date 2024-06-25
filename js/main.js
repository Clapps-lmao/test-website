// typewriter.js

document.addEventListener("DOMContentLoaded", function() {
    // Select the element where the typewriter effect will be applied
    const typewriterElement = document.getElementById("typewriter-text");
    // Get the full text content of the element
    const text = typewriterElement.textContent;
    // Clear the text content of the element
    typewriterElement.textContent = "";
    
    let index = 0;
    
    function typeWriter() {
        // Check if the current index is less than the length of the text
        if (index < text.length) {
            // Add the next character to the element's text content
            typewriterElement.textContent += text.charAt(index);
            // Increment the index
            index++;
            // Set a timeout to call the typeWriter function again after a delay
            setTimeout(typeWriter, 90); // Adjust the delay (in milliseconds) as needed
        }
    }
    
    // Start the typewriter effect
    typeWriter();
});


// slideshow.js

document.addEventListener("DOMContentLoaded", function() {
    // Slideshow functionality
    const images = [
        "imgs/1.jpg",
        "imgs/2.jpg",
        "imgs/3.jpg",
        "imgs/4.jpg",
        "imgs/5.jpg",
        "imgs/6.jpg",
        "imgs/7.jpg",
        "imgs/8.jpg",
        "imgs/9.jpg",
        "imgs/10.jpg"
    ];

    const slideshowContainer = document.getElementById('slideshow');
    const slideCounter = document.getElementById('slide-counter');
    let currentSlide = 0;

    function showSlides() {
        slideshowContainer.innerHTML = images.map((src, index) => {
            return `<div class="slide" style="display: ${index === currentSlide ? 'block' : 'none'};">
                        <img src="${src}" alt="Slide Image">
                    </div>`;
        }).join('');
        // Update the slide counter
        slideCounter.textContent = `${currentSlide + 1}/${images.length}`;
    }

    function changeSlide(n) {
        currentSlide += n;
        if (currentSlide >= images.length) {
            currentSlide = 0;
        } else if (currentSlide < 0) {
            currentSlide = images.length - 1;
        }
        showSlides();
    }

    showSlides();

    window.changeSlide = changeSlide;
});

//smoothscroll.js
const appointmenbuttonlearnmore = document.getElementById('my-work');

appointmenbuttonlearnmore.addEventListener('click', () => {
    const appointmentFullElement = document.getElementById('slideshow');
    
    if (appointmentFullElement) {
        appointmentFullElement.scrollIntoView({ behavior: 'smooth' });
    }
});