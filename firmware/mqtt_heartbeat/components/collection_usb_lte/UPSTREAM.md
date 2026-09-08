The CDC port and PPP netif wiring in `collection_usb_lte.c` is derived from
Espressif `iot_usbh_modem` 2.2.0, `src/esp_modem_dte.c` and
`src/usbh_modem.c`, commit `a2dd58acf2fef837c9d5e2e86b7e33d318b6b2ff`.
The Apache-2.0 license is retained in `LICENSE.espressif`.

The opt-in `usb_dependencies/idf_component.yml` pins modem 2.2.0, CDC 3.1.0, iot_eth 1.0.0,
modem_at 0.1.0 and cmake_utilities 0.5.3. IDF is restricted to the currently
built 5.4.2 series. No `usbh_modem_install`, daemon, retrying DTE sync, or
modem_at parser is called. Unused upstream command code is not linked.

Necessary seam changes: the existing sole modem task submits one fixed AT
command and polls a deadline; an explicit descriptor selects one USB port;
callback bytes are serialized with command state and disconnect; exact CRLF
result lines replace substring matches; cancelled/timed-out dialing leaves
the mode uncertain; PPP suffix bytes after CONNECT are retained. The outer
owner prepares PDP CID 1 over its existing UART, decides retries and network
selection, and continues GNSS/Cell. No callback issues AT commands.

The default profile is disabled and has no third-party manifest/dependencies.
To configure an enabled build, explicitly add this component's
`usb_dependencies` directory to `EXTRA_COMPONENT_DIRS` before `project()`,
then set `CONFIG_EGOLINK_COLLECTION_USB_LTE=y`. The hidden dependency Kconfig
symbol prevents enabling the driver without the dependency packet. Only that
opt-in build resolves packages/creates its dependency lock. Default Wi-Fi and
legacy builds never discover the nested packet. Init uses already initialized esp_netif and
the default event loop. Do not enable a second PPP manager or CDC installer.
The caller must poll between bounded UART operations and stop the uploader
before quiescing. Quiesce posts netif stop and prevents new PPP submissions;
it does not attest physical modem shutdown or synchronous PPP stack teardown.
Retained USB/PPP objects are intentionally not force-deleted: upstream CDC
close/uninstall and netif teardown do not offer an end-to-end caller deadline.
After quiesce, allow at least one second after the last submission, perform
ESCAPE then HANGUP, and require their actual replies. Failure remains visible.
The module continues powered for GNSS/Cell regardless of the selected network.

USB callbacks serialize port lifetime against one bounded USB write (two
25 ms waits). Only those callback-side gate acquisitions can wait for the
owner's current submission; owner begin/poll/quiesce never wait for the gate.
No response wait holds it. Underlying USB worker tasks belong to the standard
transport stack, not a second modem control owner.
