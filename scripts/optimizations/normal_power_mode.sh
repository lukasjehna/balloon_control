#!/bin/bash
# Script to restore normal mode on Raspberry Pi (Raspbian GNU/Linux 10 buster) by enabling USB, HDMI, Wi-Fi, Bluetooth, and LEDs

if [ "$EUID" -ne 0 ]; then
    echo "Please run this script as sudo."
    exit 1
fi

CONFIG_FILE="/boot/config.txt"
BACKUP_FILE="/boot/config.txt.bak_$(date +%Y%m%d_%H%M%S)"

# Backup the current config file
echo "Backing up $CONFIG_FILE to $BACKUP_FILE"
cp "$CONFIG_FILE" "$BACKUP_FILE"
if [ $? -ne 0 ]; then
    echo "Error: Failed to create backup. Aborting."
    exit 1
fi

# Re-enable USB
USB_DEVICE="1-1"
if [ -d "/sys/bus/usb/devices/$USB_DEVICE" ]; then
    echo "$USB_DEVICE" | tee /sys/bus/usb/drivers/usb/bind
    if [ $? -ne 0 ]; then
        echo "Error: Failed to rebind USB device $USB_DEVICE."
        exit 1
    else
        echo "USB device $USB_DEVICE re-enabled."
    fi
else
    echo "Warning: USB device $USB_DEVICE not found, skipping USB re-enable."
fi

# Re-enable HDMI
if ! command -v /opt/vc/bin/tvservice &> /dev/null; then
    echo "Error: tvservice not found at /opt/vc/bin/tvservice."
    exit 1
fi
if ! /opt/vc/bin/tvservice -p; then
    echo "Error: Failed to re-enable HDMI."
    exit 1
else
    echo "HDMI re-enabled."
fi

# Function to comment out a line in config.txt if it exists and is uncommented
comment_line() {
    local line="$1"
    local file="$2"
    local escaped_line=$(echo "$line" | sed 's/[\/&]/\\&/g')
    # Check if line exists and is uncommented
    if grep -Fx "$line" "$file" > /dev/null; then
        # Comment out the line by adding #
        sed -i "s/^$escaped_line/#$escaped_line/" "$file"
        echo "Commented out '$line' in $file."
    else
        echo "Line '$line' not found or already commented in $file, skipping."
    fi
}

# Comment out lines that disable Wi-Fi, Bluetooth, and LEDs
comment_line "dtoverlay=disable-wifi" "$CONFIG_FILE"
comment_line "dtoverlay=disable-bt" "$CONFIG_FILE"
comment_line "dtparam=pwr_led_trigger=none" "$CONFIG_FILE"
comment_line "dtparam=pwr_led_activelow=off" "$CONFIG_FILE"
comment_line "dtparam=act_led_trigger=none" "$CONFIG_FILE"
comment_line "dtparam=act_led_activelow=off" "$CONFIG_FILE"
comment_line "dtparam=eth_led0=4" "$CONFIG_FILE"
comment_line "dtparam=eth_led1=4" "$CONFIG_FILE"

# Verify changes in config.txt
echo "Verifying changes in $CONFIG_FILE..."
echo "Checking for active disable entries:"
if grep -Fx -e "dtoverlay=disable-wifi" -e "dtoverlay=disable-bt" -e "dtparam=pwr_led_trigger=none" -e "dtparam=pwr_led_activelow=off" -e "dtparam=act_led_trigger=none" -e "dtparam=act_led_activelow=off" -e "dtparam=eth_led0=4" -e "dtparam=eth_led1=4" "$CONFIG_FILE" > /dev/null; then
    echo "Warning: Some disable entries are still active (not commented)."
else
    echo "All disable entries successfully commented out."
fi

# Prompt for reboot
read -p "Changes require a reboot to take effect. Reboot now (y/N): " answer
if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
    echo "Rebooting..."
    sleep 5
    reboot
else
    echo "Please reboot manually to apply changes."
fi
