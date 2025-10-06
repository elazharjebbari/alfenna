(function () {
  document.addEventListener('DOMContentLoaded', function () {
    var wrapper = document.querySelector('.courses-enroll-wrapper[data-locked]');
    if (!wrapper) {
      return;
    }

    var isLocked = wrapper.getAttribute('data-locked') === '1';
    var checkoutUrl = wrapper.getAttribute('data-checkout-url') || '';
    var video = wrapper.querySelector('video');
    if (!video) {
      return;
    }

    var source = video.querySelector('source');
    var spinner = wrapper.querySelector('.loading');

    var showSpinner = function () {
      if (spinner) {
        spinner.style.display = '';
      }
    };

    var hideSpinner = function () {
      if (spinner) {
        spinner.style.display = 'none';
      }
    };

    if (!isLocked && source && source.dataset && source.dataset.src) {
      source.setAttribute('src', source.dataset.src);
      video.load();
    }

    hideSpinner();

    video.addEventListener('waiting', showSpinner);
    video.addEventListener('seeking', showSpinner);
    video.addEventListener('loadeddata', hideSpinner);
    video.addEventListener('canplay', hideSpinner);
    video.addEventListener('playing', hideSpinner);
    video.addEventListener('pause', hideSpinner);

    var playlistLinks = wrapper.querySelectorAll('.video-playlist .vids a');
    playlistLinks.forEach(function (link) {
      link.addEventListener('click', function (event) {
        if (link.classList.contains('locked')) {
          event.preventDefault();
          if (checkoutUrl) {
            window.location.href = checkoutUrl;
          }
          return;
        }

        if (isLocked) {
          return;
        }

        var dataSrc = link.getAttribute('data-src');
        if (!dataSrc || !source) {
          return;
        }

        event.preventDefault();
        if (source.getAttribute('src') !== dataSrc) {
          showSpinner();
          source.setAttribute('src', dataSrc);
          video.load();
          video.play().catch(function () {
            hideSpinner();
          });
        }

        playlistLinks.forEach(function (lnk) {
          lnk.classList.remove('active');
        });
        link.classList.add('active');
      });
    });
  });
})();
