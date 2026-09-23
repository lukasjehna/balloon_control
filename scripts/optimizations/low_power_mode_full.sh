#!/bin/bash
# Script to enable low power mode on Raspberry Pi (Raspbian GNU/Linux 10 buster) by disabling USB, HDMI, Wi-Fi, Bluetooth, and LEDs
# Add 
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

# Disable USB
USB_DEVICE="1-1"
if [ -d "/sys/bus/usb/devices/$USB_DEVICE" ]; then
    echo "$USB_DEVICE" | tee /sys/bus/usb/drivers/usb/unbind
    if [ $? -ne 0 ]; then
        echo "Error: Failed to unbind USB device $USB_DEVICE."
        exit 1
    else
        echo "USB device $USB_DEVICE disabled."
    fi
else
    echo "Warning: USB device $USB_DEVICE not found, skipping USB disable."
fi

# Disable HDMI
if ! command -v /opt/vc/bin/tvservice &> /dev/null; then
    echo "Error: tvservice not found at /opt/vc/bin/tvservice."
    exit 1
fi
if ! /opt/vc/bin/tvservice -o; then
    echo "Error: Failed to disable HDMI."
    exit 1
else
    echo "HDMI disabled."
fi

# Function to add or uncomment a line in config.txt
add_or_uncomment_line() {
    local section="$1"
    local line="$2"
    local file="$3"
    local escaped_line=$(echo "$line" | sed 's/[\/&]/\\&/g')
    local section_start line_exists commented_line

    # Check if section exists
    if grep -q "^\[$section\]" "$file"; then
        section_start=$(grep -n "^\[$section\]" "$file" | cut -d: -f1)
        # Check if line exists (uncommented)
        line_exists=$(sed -n "$section_start,/^\[/p" "$file" | grep -Fx "$line")
        # Check if line exists as commented
        commented_line=$(sed -n "$section_start,/^\[/p" "$file" | grep -Fx "#$line")
        if [ -n "$line_exists" ]; then
            echo "Line '$line' already active under [$section]. Skipping."
        elif [ -n "$commented_line" ]; then
            # Uncomment the line
            sed -i "/^#${escaped_line}$/s/^#//" "$file"
            echo "Uncommented '$line' under [$section]."
        else
            # Add line under the section
            sed -i "/^\[$section\]/a $line" "$file"
            echo "Added '$line' under [$section]."
        fi
    else
        # Add section and line
        echo -e "\n[$section]\n$line" >> "$file"
        echo "Created [$section] and added '$line'."
    fi
}

# Add or uncomment lines to disable Wi-Fi, Bluetooth, and LEDs
add_or_uncomment_line "all" "dtoverlay=disable-wifi" "$CONFIG_FILE"
add_or_uncomment_line "all" "dtoverlay=disable-bt" "$CONFIG_FILE"
add_or_uncomment_line "pi4" "dtparam=pwr_led_trigger=none" "$CONFIG_FILE"
add_or_uncomment_line "pi4" "dtparam=pwr_led_activelow=off" "$CONFIG_FILE"
add_or_uncomment_line "pi4" "dtparam=act_led_trigger=none" "$CONFIG_FILE"
add_or_uncomment_line "pi4" "dtparam=act_led_activelow=off" "$CONFIG_FILE"
add_or_uncomment_line "pi4" "dtparam=eth_led0=4" "$CONFIG_FILE"
add_or_uncomment_line "pi4" "dtparam=eth_led1=4" "$CONFIG_FILE"

# Verify changes in config.txt
echo "Verifying changes in $CONFIG_FILE..."
echo "Checking [all] section:"
if grep -A 100 "^\[all\]" "$CONFIG_FILE" | grep -Fx -e "dtoverlay=disable-wifi" -e "dtoverlay=disable-bt" | wc -l | grep -q "2"; then
    echo "Wi-Fi and Bluetooth disable entries verified."
else
    echo "Warning: Some [all] entries (Wi-Fi or Bluetooth) not found or commented."
fi
echo "Checking [pi4] section:"
if grep -A 100 "^\[pi4\]" "$CONFIG_FILE" | grep -Fx -e "dtparam=pwr_led_trigger=none" -e "dtparam=pwr_led_activelow=off" -e "dtparam=act_led_trigger=none" -e "dtparam=act_led_activelow=off" -e "dtparam=eth_led0=4" -e "dtparam=eth_led1=4" | wc -l | grep -q "6"; then
    echo "LED disable entries verified."
else
    echo "Warning: Some [pi4] entries (LEDs) not found or commented."
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
