3. The Desert Map — spec third, lighter touch
Counter-intuitive, but: the map is the demo screenshot, not the demo substance. It's the hook, not the proof. Spec it last and lighter.
Why third:

A choropleth with click-through is conceptually simpler than the audit view
It's the most forgiving surface — visual quality carries it even with thin functionality
It depends on aggregations that come from the same pipeline as the audit and console; spec'ing those two first means the map's data is essentially free
Over-spec'ing the map eats time you should spend on substance

Spec scope: region selection, capability filter, coverage radius slider, click-region drilldown into ranked facility list. Skip per-region overlays, custom basemaps, time-series. None of that ships in 36 hours.