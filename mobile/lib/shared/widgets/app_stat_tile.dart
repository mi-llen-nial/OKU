import 'package:flutter/material.dart';

class AppStatTile extends StatelessWidget {
  const AppStatTile({
    super.key,
    required this.label,
    required this.value,
    this.icon,
    this.meta,
  });

  final String label;
  final String value;
  final IconData? icon;
  final String? meta;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE5EAF2)),
      ),
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(
                    color: Color(0xFF5D677B),
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              if (icon != null)
                Icon(icon, size: 16, color: const Color(0xFF5D677B)),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            value,
            style: const TextStyle(
              fontSize: 24,
              color: Color(0xFF111827),
              fontWeight: FontWeight.w700,
            ),
          ),
          if (meta != null) ...[
            const SizedBox(height: 3),
            Text(
              meta!,
              style: const TextStyle(color: Color(0xFF5D677B), fontSize: 12),
            ),
          ],
        ],
      ),
    );
  }
}
