Three main sections:
[Unit], [Service] and [Install]
[Unit]:
After: starts [Service] only after these services are running
Wants:  starts services, but failure has no impact on the main service.
# execute theses on startup



# put journals in memory and not in ram
sudo cp /etc/systemd/journald.conf /etc/systemd/journald.conf.bak 
sudo vim /etc/systemd/journald.conf
add:
[Journal]
Storage=persistent
SystemMaxUse=500M
MaxRetentionSec=2week

# How to read logs:
sudo journalctl -u balloon-udp@chopper.service
sudo journalctl -u balloon-udp-spectrometer.service -b
sudo journalctl -u balloon-main.service
sudo journalctl -u balloon-main.service -f
sudo journalctl -u balloon-main.service --since "10 min ago"
sudo journalctl -u balloon-main.service --no-pager