# Hetzner Heartbeat agent

This is a small agent for Hetzner hosted machines to handle the management of
failover ip's (for example when using loadbalancers).

It simply does a ping to the failover ip and when it fails it sets another
ip from the address list as the active one.

# Requirements

* Python 2.7.x
* python-requests
* fping

# Is this safe for production?

Although the code may not seem as clean as it should, I can guaranteee you
that it is running on a production environment without any issues.

Fortunately over time I will clena up the code, and if I don't, feel free
to do it yourself! After all it's open source... right?... right?

# Authors

* Oscar Carballal Prego <oscar@oscarcp.com>

# License

GPLv3
