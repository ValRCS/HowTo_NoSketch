#  Crystal

Crystal is the web UI for NoSketch Engine. It is a single-page application interfacing with Bonito, the NoSketch Engine API.

## Modified index.html file

As Crystal is a single-page application, the index.html file is a simple stub with very little content.

This file is usually found in ` /var/www/crystal/` and is served by the web server (apache2) when the user navigates to the Crystal web UI.


### Fixed banner to indicate new version at a different site

We added a fixed div element of class "fixed-banner" that indicated a new version was available at a different site - korpuss.lnb.lv - and a link to the new version.

Also we added a script to move the fixed element to bottom right corner of the screen after a timeout of 10 seconds.

With this approach we do not have to force users to update the version, but we can inform them about the new version and provide a link to it.

Also we avoid rebuilding the crystal itself (done using node) and has potentially unwanted side effects.

