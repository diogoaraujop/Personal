# Laptop migration

Clone this repository, install each tool's requirements, and transfer local settings separately. Password.txt and *.local-secret files are deliberately excluded from GitHub. Copy the punch_lunch/chime-webhook.local-secret file (and the archive copy if required) to the same relative paths on the new laptop, or use the existing webhook environment variable supported by each script. The current laptop retains these files and continues using them.

The amazon_iphone_monitor/Password.txt file must be transferred privately. Virtual environments and build outputs are excluded and can be recreated.
