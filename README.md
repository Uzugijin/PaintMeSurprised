# PaintMeSurprised
Baking assist addon for [TAM](https://uzugijin.github.io/pages/tam.html) modeling.

How to install the lazy way:  
Drop the .py into ->  
C:\Users\username\AppData\Roaming\Blender Foundation\Blender\blenderversion\scripts\addons  
Open Blender and go to Preferences > Add-ons and start typing PaintMeSurprised. Click on the checkbox to active.

Known issues and quirks:  
-> Input image will be saved on every Record button push in order for the addon to work correctly!  
  -> Undo works, but for images it only if the image is packed because a saved external image is overwritten forever, so it is advised to pack the input image into the blend file.  
-> After bake, last node link may not reconnect properly within certain setups.  
